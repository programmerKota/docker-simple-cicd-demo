from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pyoxigraph import Literal, NamedNode, Quad, QuerySolutions, Store

from ..integrations.home_assistant import HomeAssistantError
from ..integrations.home_assistant_ws import HomeAssistantSnapshot, HomeAssistantWebSocketClient

RDF_TYPE = NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
RDFS_LABEL = NamedNode("http://www.w3.org/2000/01/rdf-schema#label")
BRICK = "https://brickschema.org/schema/Brick#"
JARVIS = "urn:jarvis:ontology:"

BRICK_ROOM = NamedNode(f"{BRICK}Room")
BRICK_EQUIPMENT = NamedNode(f"{BRICK}Equipment")
BRICK_POINT = NamedNode(f"{BRICK}Point")
BRICK_SENSOR = NamedNode(f"{BRICK}Sensor")
BRICK_HAS_LOCATION = NamedNode(f"{BRICK}hasLocation")
BRICK_HAS_POINT = NamedNode(f"{BRICK}hasPoint")
BRICK_IS_POINT_OF = NamedNode(f"{BRICK}isPointOf")

JARVIS_HA_ENTITY = NamedNode(f"{JARVIS}HomeAssistantEntity")
JARVIS_ENTITY_ID = NamedNode(f"{JARVIS}entityId")
JARVIS_DOMAIN = NamedNode(f"{JARVIS}domain")
JARVIS_REPORTED_STATE = NamedNode(f"{JARVIS}reportedState")
JARVIS_LAST_CHANGED = NamedNode(f"{JARVIS}lastChanged")
JARVIS_AVAILABLE = NamedNode(f"{JARVIS}available")
JARVIS_ENABLED = NamedNode(f"{JARVIS}enabled")
JARVIS_PLATFORM = NamedNode(f"{JARVIS}platform")
JARVIS_DEVICE_CLASS = NamedNode(f"{JARVIS}deviceClass")
JARVIS_UNIT = NamedNode(f"{JARVIS}unitOfMeasurement")
JARVIS_RESOLVED_AREA = NamedNode(f"{JARVIS}resolvedArea")
JARVIS_AREA_ID = NamedNode(f"{JARVIS}areaId")
JARVIS_DEVICE_ID = NamedNode(f"{JARVIS}deviceId")
JARVIS_MANUFACTURER = NamedNode(f"{JARVIS}manufacturer")
JARVIS_MODEL = NamedNode(f"{JARVIS}model")
JARVIS_SNAPSHOT_HASH = NamedNode(f"{JARVIS}snapshotHash")
JARVIS_CAPTURED_AT = NamedNode(f"{JARVIS}capturedAt")
JARVIS_ACTIVE_GRAPH = NamedNode(f"{JARVIS}activeGraph")
JARVIS_LAST_SUCCESSFUL_SYNC = NamedNode(f"{JARVIS}lastSuccessfulSync")
JARVIS_LAST_SYNC_ERROR = NamedNode(f"{JARVIS}lastSyncError")
JARVIS_SOURCE = NamedNode(f"{JARVIS}source")

TWIN_ROOT = NamedNode("urn:jarvis:twin")
METADATA_GRAPH = NamedNode("urn:jarvis:graph:metadata")


class HouseholdTwin:
    """Persistent last-known-good household semantics and reported state."""

    def __init__(
        self,
        store_path: Path,
        client: HomeAssistantWebSocketClient,
        *,
        refresh_interval_seconds: float = 60.0,
    ):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = Store(str(store_path))
        self.client = client
        self.refresh_interval_seconds = refresh_interval_seconds
        self._lock = threading.RLock()
        self._refresh_lock = asyncio.Lock()
        self._last_error: str | None = None

    async def ensure_fresh(self) -> dict[str, Any]:
        status = self.status()
        if status["ready"] and status["age_seconds"] is not None:
            if status["age_seconds"] <= self.refresh_interval_seconds:
                return status
        async with self._refresh_lock:
            status = self.status()
            if status["ready"] and status["age_seconds"] is not None:
                if status["age_seconds"] <= self.refresh_interval_seconds:
                    return status
            try:
                snapshot = await self.client.fetch_snapshot()
                self.replace_snapshot(snapshot)
                self._last_error = None
            except Exception as exc:
                self._last_error = self._safe_error(exc)
                self._record_sync_error(self._last_error)
                if not self.status()["ready"]:
                    raise HomeAssistantError("No usable household twin snapshot is available") from exc
            return self.status()

    def replace_snapshot(self, snapshot: HomeAssistantSnapshot) -> dict[str, Any]:
        snapshot_hash = self._snapshot_hash(snapshot)
        graph = NamedNode(f"urn:jarvis:snapshot:{snapshot_hash}")
        quads = self._build_quads(snapshot, snapshot_hash, graph)
        with self._lock:
            active_before = self._active_graph()
            if active_before != graph:
                with context_suppress_graph_error():
                    self.store.remove_graph(graph)
                self.store.bulk_extend(quads)
                self._replace_metadata_node(JARVIS_ACTIVE_GRAPH, graph)
                if active_before is not None and active_before != graph:
                    self.store.remove_graph(active_before)
            self._replace_metadata_node(JARVIS_LAST_SUCCESSFUL_SYNC, Literal(snapshot.captured_at))
            self._remove_metadata(JARVIS_LAST_SYNC_ERROR)
            self.store.flush()
        return self.summary()

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = self._active_graph()
            last_sync = self._metadata_literal(JARVIS_LAST_SUCCESSFUL_SYNC)
            age: float | None = None
            if last_sync:
                try:
                    age = max(
                        0.0,
                        (datetime.now(UTC) - datetime.fromisoformat(last_sync)).total_seconds(),
                    )
                except ValueError:
                    age = None
            return {
                "ready": active is not None,
                "active_graph": active.value if active else None,
                "last_successful_sync": last_sync,
                "age_seconds": age,
                "stale": active is not None and (age is None or age > self.refresh_interval_seconds),
                "last_error": self._last_error or self._metadata_literal(JARVIS_LAST_SYNC_ERROR),
            }

    def summary(self) -> dict[str, Any]:
        with self._lock:
            graph = self._require_active_graph()
            status = self.status()
            return {
                **status,
                "snapshot_hash": self._graph_literal(graph, TWIN_ROOT, JARVIS_SNAPSHOT_HASH),
                "captured_at": self._graph_literal(graph, TWIN_ROOT, JARVIS_CAPTURED_AT),
                "areas": self._count_type(graph, BRICK_ROOM),
                "devices": self._count_type(graph, BRICK_EQUIPMENT),
                "entities": self._count_type(graph, JARVIS_HA_ENTITY),
                "sensors": self._count_type(graph, BRICK_SENSOR),
            }

    def find_entities(
        self,
        *,
        room: str = "",
        domain: str = "",
        state: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        room_filter = room.strip().casefold()
        domain_filter = domain.strip().casefold()
        state_filter = state.strip().casefold()
        bounded_limit = min(max(int(limit), 1), 200)
        records = self._all_entities()
        matches = []
        for record in records:
            if room_filter and room_filter not in str(record.get("area_name") or "").casefold():
                continue
            if domain_filter and domain_filter != str(record["domain"]).casefold():
                continue
            if state_filter and state_filter != str(record["state"]).casefold():
                continue
            matches.append(record)
            if len(matches) >= bounded_limit:
                break
        return matches

    def explain_entity(self, entity_id: str) -> dict[str, Any]:
        normalized = entity_id.strip().lower()
        for record in self._all_entities():
            if record["entity_id"] == normalized:
                return {
                    **record,
                    "explanation": self._explanation(record),
                    "twin": self.status(),
                }
        raise KeyError(normalized)

    def _all_entities(self) -> list[dict[str, Any]]:
        with self._lock:
            graph = self._require_active_graph()
            query = f"""
PREFIX jarvis: <{JARVIS}>
PREFIX brick: <{BRICK}>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?entity ?entity_id ?name ?domain ?state ?available ?enabled
       ?last_changed ?platform ?device_class ?unit ?area_name ?device_name
WHERE {{
  GRAPH <{graph.value}> {{
    ?entity a jarvis:HomeAssistantEntity ;
            jarvis:entityId ?entity_id ;
            rdfs:label ?name ;
            jarvis:domain ?domain ;
            jarvis:reportedState ?state ;
            jarvis:available ?available ;
            jarvis:enabled ?enabled .
    OPTIONAL {{ ?entity jarvis:lastChanged ?last_changed . }}
    OPTIONAL {{ ?entity jarvis:platform ?platform . }}
    OPTIONAL {{ ?entity jarvis:deviceClass ?device_class . }}
    OPTIONAL {{ ?entity jarvis:unitOfMeasurement ?unit . }}
    OPTIONAL {{ ?entity jarvis:resolvedArea ?area . ?area rdfs:label ?area_name . }}
    OPTIONAL {{ ?entity brick:isPointOf ?device . ?device rdfs:label ?device_name . }}
  }}
}}
ORDER BY LCASE(STR(?name)) STR(?entity_id)
"""
            results = self.store.query(query)
            if not isinstance(results, QuerySolutions):
                return []
            records: list[dict[str, Any]] = []
            for row in results:
                records.append(
                    {
                        "entity_id": self._binding(row, "entity_id") or "",
                        "name": self._binding(row, "name") or "",
                        "domain": self._binding(row, "domain") or "",
                        "state": self._binding(row, "state") or "unknown",
                        "available": self._bool_binding(row, "available"),
                        "enabled": self._bool_binding(row, "enabled"),
                        "last_changed": self._binding(row, "last_changed"),
                        "platform": self._binding(row, "platform"),
                        "device_class": self._binding(row, "device_class"),
                        "unit": self._binding(row, "unit"),
                        "area_name": self._binding(row, "area_name"),
                        "device_name": self._binding(row, "device_name"),
                    }
                )
            return records

    def _build_quads(
        self,
        snapshot: HomeAssistantSnapshot,
        snapshot_hash: str,
        graph: NamedNode,
    ) -> list[Quad]:
        quads: list[Quad] = [
            Quad(TWIN_ROOT, JARVIS_SNAPSHOT_HASH, Literal(snapshot_hash), graph),
            Quad(TWIN_ROOT, JARVIS_CAPTURED_AT, Literal(snapshot.captured_at), graph),
            Quad(TWIN_ROOT, JARVIS_SOURCE, Literal("home-assistant"), graph),
        ]
        areas = {str(item.get("area_id")): item for item in snapshot.areas if item.get("area_id")}
        devices = {str(item.get("id")): item for item in snapshot.devices if item.get("id")}
        entities = {
            str(item.get("entity_id")): item
            for item in snapshot.entities
            if item.get("entity_id")
        }
        states = {str(item.get("entity_id")): item for item in snapshot.states if item.get("entity_id")}

        for area_id, area in sorted(areas.items()):
            area_node = self._node("area", area_id)
            quads.extend(
                [
                    Quad(area_node, RDF_TYPE, BRICK_ROOM, graph),
                    Quad(area_node, RDFS_LABEL, Literal(str(area.get("name") or area_id)), graph),
                    Quad(area_node, JARVIS_AREA_ID, Literal(area_id), graph),
                ]
            )

        for device_id, device in sorted(devices.items()):
            device_node = self._node("device", device_id)
            name = device.get("name_by_user") or device.get("name") or device_id
            quads.extend(
                [
                    Quad(device_node, RDF_TYPE, BRICK_EQUIPMENT, graph),
                    Quad(device_node, RDFS_LABEL, Literal(str(name)), graph),
                    Quad(device_node, JARVIS_DEVICE_ID, Literal(device_id), graph),
                ]
            )
            self._optional_literal(quads, device_node, JARVIS_MANUFACTURER, device.get("manufacturer"), graph)
            self._optional_literal(quads, device_node, JARVIS_MODEL, device.get("model"), graph)
            area_id = device.get("area_id")
            if area_id and str(area_id) in areas:
                quads.append(
                    Quad(device_node, BRICK_HAS_LOCATION, self._node("area", str(area_id)), graph)
                )

        for entity_id in sorted(set(entities) | set(states)):
            registry = entities.get(entity_id, {})
            state = states.get(entity_id)
            attributes = state.get("attributes") if isinstance(state, dict) else {}
            if not isinstance(attributes, dict):
                attributes = {}
            domain = entity_id.split(".", 1)[0]
            entity_node = self._node("entity", entity_id)
            name = (
                attributes.get("friendly_name")
                or registry.get("name")
                or registry.get("original_name")
                or entity_id
            )
            reported_state = str(state.get("state")) if state and state.get("state") is not None else "unknown"
            available = state is not None and reported_state not in {"unavailable", "unknown"}
            enabled = registry.get("disabled_by") is None
            quads.extend(
                [
                    Quad(entity_node, RDF_TYPE, JARVIS_HA_ENTITY, graph),
                    Quad(entity_node, RDF_TYPE, BRICK_POINT, graph),
                    Quad(entity_node, JARVIS_ENTITY_ID, Literal(entity_id), graph),
                    Quad(entity_node, RDFS_LABEL, Literal(str(name)), graph),
                    Quad(entity_node, JARVIS_DOMAIN, Literal(domain), graph),
                    Quad(entity_node, JARVIS_REPORTED_STATE, Literal(reported_state), graph),
                    Quad(entity_node, JARVIS_AVAILABLE, Literal(available), graph),
                    Quad(entity_node, JARVIS_ENABLED, Literal(enabled), graph),
                    Quad(entity_node, JARVIS_SOURCE, Literal("home-assistant"), graph),
                ]
            )
            if domain in {"sensor", "binary_sensor"}:
                quads.append(Quad(entity_node, RDF_TYPE, BRICK_SENSOR, graph))
            self._optional_literal(quads, entity_node, JARVIS_LAST_CHANGED, state.get("last_changed") if state else None, graph)
            self._optional_literal(quads, entity_node, JARVIS_PLATFORM, registry.get("platform"), graph)
            self._optional_literal(
                quads,
                entity_node,
                JARVIS_DEVICE_CLASS,
                attributes.get("device_class") or registry.get("device_class"),
                graph,
            )
            self._optional_literal(
                quads,
                entity_node,
                JARVIS_UNIT,
                attributes.get("unit_of_measurement"),
                graph,
            )

            device_id = registry.get("device_id")
            if device_id and str(device_id) in devices:
                device_node = self._node("device", str(device_id))
                quads.append(Quad(device_node, BRICK_HAS_POINT, entity_node, graph))
                quads.append(Quad(entity_node, BRICK_IS_POINT_OF, device_node, graph))

            explicit_area = registry.get("area_id")
            device_area = devices.get(str(device_id), {}).get("area_id") if device_id else None
            resolved_area = explicit_area or device_area
            if resolved_area and str(resolved_area) in areas:
                area_node = self._node("area", str(resolved_area))
                quads.append(Quad(entity_node, JARVIS_RESOLVED_AREA, area_node, graph))
                if not device_id:
                    quads.append(Quad(entity_node, BRICK_HAS_LOCATION, area_node, graph))
        return quads

    def _active_graph(self) -> NamedNode | None:
        values = list(
            self.store.quads_for_pattern(
                TWIN_ROOT,
                JARVIS_ACTIVE_GRAPH,
                None,
                METADATA_GRAPH,
            )
        )
        if not values or not isinstance(values[0].object, NamedNode):
            return None
        return values[0].object

    def _require_active_graph(self) -> NamedNode:
        graph = self._active_graph()
        if graph is None:
            raise RuntimeError("Household twin has no successful snapshot")
        return graph

    def _replace_metadata_node(self, predicate: NamedNode, value: NamedNode | Literal) -> None:
        self._remove_metadata(predicate)
        self.store.add(Quad(TWIN_ROOT, predicate, value, METADATA_GRAPH))

    def _remove_metadata(self, predicate: NamedNode) -> None:
        for quad in list(
            self.store.quads_for_pattern(TWIN_ROOT, predicate, None, METADATA_GRAPH)
        ):
            self.store.remove(quad)

    def _record_sync_error(self, error: str) -> None:
        with self._lock:
            self._replace_metadata_node(JARVIS_LAST_SYNC_ERROR, Literal(error))
            self.store.flush()

    def _metadata_literal(self, predicate: NamedNode) -> str | None:
        values = list(
            self.store.quads_for_pattern(TWIN_ROOT, predicate, None, METADATA_GRAPH)
        )
        if not values or not isinstance(values[0].object, Literal):
            return None
        return values[0].object.value

    def _graph_literal(
        self,
        graph: NamedNode,
        subject: NamedNode,
        predicate: NamedNode,
    ) -> str | None:
        values = list(self.store.quads_for_pattern(subject, predicate, None, graph))
        if not values or not isinstance(values[0].object, Literal):
            return None
        return values[0].object.value

    def _count_type(self, graph: NamedNode, type_node: NamedNode) -> int:
        return len(list(self.store.quads_for_pattern(None, RDF_TYPE, type_node, graph)))

    @staticmethod
    def _binding(row: Any, name: str) -> str | None:
        value = row[name]
        return value.value if value is not None else None

    @classmethod
    def _bool_binding(cls, row: Any, name: str) -> bool:
        return str(cls._binding(row, name)).lower() == "true"

    @staticmethod
    def _node(kind: str, value: str) -> NamedNode:
        return NamedNode(f"urn:jarvis:{kind}:{quote(value, safe='')}")

    @staticmethod
    def _optional_literal(
        quads: list[Quad],
        subject: NamedNode,
        predicate: NamedNode,
        value: Any,
        graph: NamedNode,
    ) -> None:
        if value is not None and str(value) != "":
            quads.append(Quad(subject, predicate, Literal(str(value)), graph))

    @staticmethod
    def _snapshot_hash(snapshot: HomeAssistantSnapshot) -> str:
        def sorted_objects(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
            return sorted(items, key=lambda item: str(item.get(key) or ""))

        canonical = json.dumps(
            {
                "areas": sorted_objects(snapshot.areas, "area_id"),
                "devices": sorted_objects(snapshot.devices, "id"),
                "entities": sorted_objects(snapshot.entities, "entity_id"),
                "states": sorted_objects(snapshot.states, "entity_id"),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, HomeAssistantError):
            return str(exc)[:500]
        return f"{type(exc).__name__}: twin synchronization failed"

    @staticmethod
    def _explanation(record: dict[str, Any]) -> str:
        location = record.get("area_name") or "部屋未設定"
        device = record.get("device_name") or "独立エンティティ"
        availability = "利用可能" if record.get("available") else "利用不可または状態不明"
        return (
            f"{record['name']} は {location} に解決された {record['domain']} エンティティです。"
            f"所属機器は {device}、現在状態は {record['state']}、{availability}です。"
        )


class context_suppress_graph_error:
    """Limit suppression to deleting a not-yet-created snapshot graph."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> bool:
        return isinstance(exc, OSError)
