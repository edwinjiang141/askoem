from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlsplit
import re

import httpx

from src.auth_session import OemSession


@dataclass
class OemDataBundle:
    target: dict[str, Any]
    latest_data: list[dict[str, Any]]
    metric_time_series: list[dict[str, Any]]
    incidents: list[dict[str, Any]]
    events: list[dict[str, Any]]


class OemClient:
    def __init__(self, timeout_seconds: int, verify_ssl: bool):
        self._timeout = timeout_seconds
        self._verify_ssl = verify_ssl

    def login(
        self,
        base_url: str,
        targets_endpoint: str,
        username: str,
        password: str,
    ) -> Optional[str]:
        # EM REST 官方方式使用 Basic Auth。这里通过最小查询验证账号可用。
        url = self._build_url(base_url, targets_endpoint)
        try:
            with httpx.Client(timeout=self._timeout, verify=self._verify_ssl) as client:
                resp = client.get(url, auth=(username, password), params={"limit": 1})
                resp.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"OEM 登录失败: {exc}") from exc
        # 当前 MVP 不依赖 token，认证凭据通过会话缓存复用。
        return None

    def fetch_bundle(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        target_name: str | None,
        route_config: dict[str, Any],
        time_range: str,
    ) -> OemDataBundle:
        if not target_name:
            return OemDataBundle(
                target={},
                latest_data=[],
                metric_time_series=[],
                incidents=[],
                events=[],
            )

        end_time = datetime.now(timezone.utc)
        start_time = self._start_time_by_range(end_time, time_range)
        target_type_name = route_config.get("target_type_name", "host")
        metric_group_name = route_config.get("metric_group_name")
        metric_name = route_config.get("metric_name")
        if not metric_group_name or not metric_name:
            raise ValueError("路由配置缺少 metric_group_name 或 metric_name。")

        target = self._resolve_target(
            session=session,
            endpoints=endpoints,
            target_name=target_name,
            target_type_name=target_type_name,
        )
        target_id = target.get("id")
        if not target_id:
            raise RuntimeError(f"未找到目标: {target_name}")

        latest_endpoint = endpoints["latest_data_by_target"].format(
            targetId=target_id,
            metricGroupName=metric_group_name,
        )
        latest_data = self._get_json(
            session.oem_base_url,
            latest_endpoint,
            auth=(session.username, session.password),
            params={"metricName": metric_name, "limit": 200},
        )
        metric_time_series = self._get_json(
            session.oem_base_url,
            endpoints["metric_time_series"],
            auth=(session.username, session.password),
            params={
                "targetId": target_id,
                "metricGroupName": metric_group_name,
                "metricName": metric_name,
                "timeCollectedGreaterThanOrEqualTo": self._format_em_time(start_time),
                "timeCollectedLessThan": self._format_em_time(end_time),
                "limit": 200,
            },
        )
        incidents = self._get_json(
            session.oem_base_url,
            endpoints["incidents"],
            auth=(session.username, session.password),
            params={
                "targetName": target_name,
                "targetTypeName": target_type_name,
                "ageInHoursLessThanOrEqualTo": self._range_hours(time_range),
                "limit": 20,
            },
        )
        events = self._fetch_events_from_incidents(
            base_url=session.oem_base_url,
            auth=(session.username, session.password),
            incident_events_endpoint=endpoints["incident_events"],
            incidents=incidents,
        )

        return OemDataBundle(
            target=target,
            latest_data=_as_list(latest_data),
            metric_time_series=_as_list(metric_time_series),
            incidents=_as_list(incidents),
            events=_as_list(events),
        )

    def list_recent_incidents(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        target_name: str | None = None,
        target_type_name: str | None = None,
        age_hours: int = 24,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "ageInHoursLessThanOrEqualTo": max(1, age_hours),
            "limit": max(1, min(limit, 200)),
        }
        if target_name:
            params["targetName"] = target_name
        if target_type_name:
            params["targetTypeName"] = target_type_name
        # [临时兼容策略 - 请勿删除]
        # 当前测试环境 OEM 版本较低，不支持 /em/api/incidents 接口。
        # 为了先跑通“告警识别 -> SOP 输出”的整体链路，这里暂时屏蔽真实 incidents 拉取，
        # 直接返回一个模拟 incidents 样本给后续流程使用。
        #
        # 等 OEM 版本升级后，恢复下面注释掉的真实调用代码即可：
        # payload = self._get_json(
        #     session.oem_base_url,
        #     endpoints["incidents"],
        #     auth=(session.username, session.password),
        #     params=params,
        # )
        # return _extract_items(payload)
        return [self._build_mock_incident(target_name=target_name, target_type_name=target_type_name)]

    @staticmethod
    def _build_mock_incident(target_name: str | None, target_type_name: str | None) -> dict[str, Any]:
        return {
            "id": "MOCK-INCIDENT-001",
            "name": "Mock Incident For Low OEM Version",
            "severity": "CRITICAL",
            "status": "OPEN",
            "message": "模拟告警：当前环境暂不支持 incidents API，使用模拟数据跑通流程。",
            "targetName": target_name or "mock-target",
            "targetTypeName": target_type_name or "host",
            "source": "mock_fallback",
        }
        payload = self._get_json(
            session.oem_base_url,
            endpoints["incidents"],
            auth=(session.username, session.password),
            params=params,
        )
        return _extract_items(payload)

    def list_events_by_incidents(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        incidents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self._fetch_events_from_incidents(
            base_url=session.oem_base_url,
            auth=(session.username, session.password),
            incident_events_endpoint=endpoints["incident_events"],
            incidents=incidents,
        )

    def list_metric_groups(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        target_name: str,
        target_type_name: str = "host",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        target = self._resolve_target(
            session=session,
            endpoints=endpoints,
            target_name=target_name,
            target_type_name=target_type_name,
        )
        target_id = target.get("id")
        if not target_id:
            raise RuntimeError(f"未找到目标: {target_name}")

        endpoint_template = endpoints.get("metric_groups_by_target", "/em/api/targets/{targetId}/metricGroups")
        endpoint = endpoint_template.format(targetId=target_id)
        try:
            payload = self._get_json(
                session.oem_base_url,
                endpoint,
                auth=(session.username, session.password),
                params={"limit": max(1, min(limit, 500))},
            )
            return _extract_items(payload)
        except RuntimeError as exc:
            # 部分环境未开放该接口，降级为空列表，避免中断整体问答流程。
            if "404" in str(exc):
                return []
            raise

    def list_targets(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        target_type_name: str = "host",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        # 这里不走 page token 分页。部分 OEM 环境会对 page 参数返回 404。
        # MVP 阶段采用单次大页查询，优先保证稳定性。
        safe_limit = max(1, min(limit, 200))
        primary = self._query_targets(
            session=session,
            endpoints=endpoints,
            params={
                "typeName": target_type_name,
                "limit": safe_limit,
                "sort": "name:ASC",
                "include": "targetStatus,total",
            },
        )
        # 某些 OEM 环境 typeName 过滤并不稳定，这里补一轮不带 typeName 的查询再做本地过滤。
        fallback = self._query_targets(
            session=session,
            endpoints=endpoints,
            params={
                "limit": safe_limit,
                "sort": "name:ASC",
                "include": "targetStatus,total",
            },
        )
        merged = self._merge_targets(primary + fallback)
        filtered = self._filter_targets_by_type(merged, target_type_name)
        return filtered if filtered else merged

    def list_hosts_with_details(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        limit: int = 50,
    ) -> list[dict[str, str]]:
        hosts = self.list_targets(
            session=session,
            endpoints=endpoints,
            target_type_name="host",
            limit=limit,
        )
        rows: list[dict[str, str]] = []
        for host in hosts:
            target_id = str(host.get("id", "")).strip()
            prop_map: dict[str, str] = self._flatten_primitives(host)
            if target_id:
                details = self._get_target_detail(session, endpoints, target_id)
                detail_map = self._flatten_primitives(details)
                for k, v in detail_map.items():
                    prop_map.setdefault(k, v)
                properties_map = self._get_target_properties(session, endpoints, target_id)
                for k, v in properties_map.items():
                    prop_map.setdefault(k, v)
            row = {
                "HostName": self._safe_text(host.get("name", "-")),
                "Status": self._pick_status_value(host, prop_map),
                "BootTime": self._pick_property_value(
                    prop_map,
                    [
                        "last boot time",
                        "boot time",
                        "last_startup_time",
                        "host_boot_time",
                        "lastbootup",
                        "lastboottime",
                        "boottime",
                        "boottimestamp",
                    ],
                    fallback_tokens=[("boot",), ("startup",), ("start", "time")],
                ),
                "IP": self._pick_property_value(
                    prop_map,
                    [
                        "ip address",
                        "host ip",
                        "ip",
                        "host_ip_address",
                        "ipaddress",
                        "ipv4address",
                        "hostipaddress",
                    ],
                    fallback_tokens=[("ip",), ("address", "ip"), ("host", "ip")],
                    prefer_ip_value=True,
                ),
                "OS": self._pick_property_value(
                    prop_map,
                    [
                        "operating system",
                        "os",
                        "os name",
                        "osname",
                        "operatingsystemname",
                    ],
                    fallback_tokens=[("operating", "system"), ("os",)],
                ),
                "Version": self._pick_property_value(
                    prop_map,
                    [
                        "version",
                        "os version",
                        "operating system version",
                        "osversion",
                        "agentversion",
                    ],
                    fallback_tokens=[("version",), ("release",)],
                ),
            }
            rows.append(row)
        return rows

    @staticmethod
    def _pick_status_value(host_obj: dict[str, Any], prop_map: dict[str, str]) -> str:
        raw_status = host_obj.get("status")
        if isinstance(raw_status, str):
            val = OemClient._safe_text(raw_status)
            if val != "-":
                return val
        if isinstance(raw_status, dict):
            for key in ("name", "value", "displayName", "status"):
                val = OemClient._safe_text(raw_status.get(key, ""))
                if val != "-":
                    return val

        # 兜底: 从详情/属性扁平键中找状态字段
        return OemClient._pick_property_value(
            prop_map,
            candidates=[
                "status",
                "target status",
                "targetstatus",
                "availability status",
                "availabilitystatus",
                "host status",
            ],
            fallback_tokens=[("status",), ("availability", "status")],
        )

    def _get_json(
        self,
        base_url: str,
        endpoint: str,
        auth: tuple[str, str] | None,
        params: dict[str, Any],
    ) -> Any:
        url = self._build_url(base_url, endpoint)
        try:
            with httpx.Client(timeout=self._timeout, verify=self._verify_ssl) as client:
                resp = client.get(url, auth=auth, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            raise RuntimeError(f"OEM 接口调用失败: {endpoint} -> {exc}") from exc

    @staticmethod
    def _start_time_by_range(end_time: datetime, time_range: str) -> datetime:
        if time_range == "1h":
            return end_time - timedelta(hours=1)
        if time_range == "7d":
            return end_time - timedelta(days=7)
        return end_time - timedelta(hours=24)

    @staticmethod
    def _format_em_time(value: datetime) -> str:
        utc = value.astimezone(timezone.utc)
        return utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    @staticmethod
    def _range_hours(time_range: str) -> int:
        if time_range == "1h":
            return 1
        if time_range == "7d":
            return 168
        return 24

    @staticmethod
    def _pick_target(target_collection: Any, target_name: str) -> dict[str, Any]:
        if not isinstance(target_collection, dict):
            return {}
        items = target_collection.get("items")
        if not isinstance(items, list):
            return {}
        expected = target_name.strip().lower()
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip().lower()
            if name == expected:
                return item
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip().lower()
            if name.startswith(expected):
                return item
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip().lower()
            if expected in name:
                return item
        for item in items:
            if isinstance(item, dict):
                return item
        return {}

    def _resolve_target(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        target_name: str,
        target_type_name: str,
    ) -> dict[str, Any]:
        candidate_queries = [
            {"name": target_name, "typeName": target_type_name, "limit": 20},
            {"nameMatches": target_name, "typeName": target_type_name, "limit": 20},
            {"nameMatches": f"{target_name}%", "typeName": target_type_name, "limit": 20},
            {"nameMatches": f"%{target_name}%", "typeName": target_type_name, "limit": 20},
            {"name": target_name, "limit": 20},
            {"nameMatches": f"{target_name}%", "limit": 20},
            {"nameMatches": f"%{target_name}%", "limit": 20},
        ]

        merged: list[dict[str, Any]] = []
        for params in candidate_queries:
            items = self._query_targets(session=session, endpoints=endpoints, params=params)
            merged = self._merge_targets(merged + items)

        filtered = self._filter_targets_by_type(merged, target_type_name)
        picked = self._pick_target({"items": filtered}, target_name)
        if picked:
            return picked

        # 最后兜底：不按类型过滤再选一次，避免误判导致空结果。
        return self._pick_target({"items": merged}, target_name)

    def _query_targets(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            payload = self._get_json(
                session.oem_base_url,
                endpoints["targets"],
                auth=(session.username, session.password),
                params=params,
            )
            return _extract_items(payload)
        except RuntimeError as exc:
            # 某些 OEM 版本不支持 include=targetStatus,total，出现 400 时去掉 include 自动重试。
            if "400" in str(exc) and "include" in params:
                fallback_params = dict(params)
                fallback_params.pop("include", None)
                payload = self._get_json(
                    session.oem_base_url,
                    endpoints["targets"],
                    auth=(session.username, session.password),
                    params=fallback_params,
                )
                return _extract_items(payload)
            raise

    def _query_targets_paginated(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        params: dict[str, Any],
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        page_count = 0
        next_page: str | None = None
        while page_count < max_pages:
            query = dict(params)
            if next_page:
                query["page"] = next_page
            try:
                payload = self._get_json(
                    session.oem_base_url,
                    endpoints["targets"],
                    auth=(session.username, session.password),
                    params=query,
                )
            except RuntimeError:
                # 分页接口在部分 OEM 环境不稳定，出现错误时返回已获取数据。
                break
            all_items.extend(_extract_items(payload))
            next_page = _extract_next_page_token(payload)
            if not next_page:
                break
            page_count += 1
        return all_items

    def _get_target_properties(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        target_id: str,
    ) -> dict[str, str]:
        endpoint_template = endpoints.get("target_properties_by_target", "/em/api/targets/{targetId}/properties")
        endpoint = endpoint_template.format(targetId=target_id)
        try:
            payload = self._get_json(
                session.oem_base_url,
                endpoint,
                auth=(session.username, session.password),
                params={"limit": 500},
            )
        except RuntimeError:
            return {}
        return self._normalize_property_payload(payload)

    def _get_target_detail(
        self,
        session: OemSession,
        endpoints: dict[str, str],
        target_id: str,
    ) -> dict[str, Any]:
        endpoint_template = endpoints.get("target_by_id", "/em/api/targets/{targetId}")
        endpoint = endpoint_template.format(targetId=target_id)
        try:
            payload = self._get_json(
                session.oem_base_url,
                endpoint,
                auth=(session.username, session.password),
                params={},
            )
        except RuntimeError:
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    @staticmethod
    def _merge_targets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in items:
            target_id = str(item.get("id", "")).strip()
            name = str(item.get("name", "")).strip()
            key = target_id or name
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    @staticmethod
    def _filter_targets_by_type(items: list[dict[str, Any]], target_type_name: str) -> list[dict[str, Any]]:
        if not items:
            return []
        expected = target_type_name.lower()
        result: list[dict[str, Any]] = []
        for item in items:
            t_name = str(item.get("typeName", "")).lower()
            t_display = str(item.get("typeDisplayName", "")).lower()
            if t_name == expected:
                result.append(item)
                continue
            if expected == "host" and (
                "host" in t_name or "host" in t_display or "主机" in t_display
            ):
                result.append(item)
                continue
            if expected == "oracle_database" and ("database" in t_display or "数据库" in t_display):
                result.append(item)
                continue
        return result

    @staticmethod
    def _normalize_property_payload(payload: Any) -> dict[str, str]:
        prop_map: dict[str, str] = {}

        def put(key: Any, value: Any) -> None:
            k = OemClient._norm_key(str(key))
            v = OemClient._safe_text(value)
            if not k or not v or v == "-":
                return
            if k not in prop_map:
                prop_map[k] = v

        # 关键修复: 你的环境 /properties 返回数组。
        # 例如: [{"name":"Boottime","value":"..."}, ...]
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                key = item.get("name") or item.get("propertyName") or item.get("key")
                value = item.get("value") or item.get("propertyValue") or item.get("displayValue")
                if key is not None:
                    put(key, value)
            return prop_map

        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("name") or item.get("propertyName") or item.get("key")
                    value = item.get("value") or item.get("propertyValue") or item.get("displayValue")
                    if key is not None:
                        put(key, value)
            props = payload.get("properties")
            if isinstance(props, list):
                for item in props:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("name") or item.get("propertyName") or item.get("key")
                    value = item.get("value") or item.get("propertyValue") or item.get("displayValue")
                    if key is not None:
                        put(key, value)
            elif isinstance(props, dict):
                for k, v in props.items():
                    put(k, v)
            for k, v in payload.items():
                if isinstance(v, (str, int, float, bool)):
                    put(k, v)
        return prop_map

    @staticmethod
    def _flatten_primitives(payload: Any) -> dict[str, str]:
        out: dict[str, str] = {}

        def walk(node: Any, prefix: str = "") -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    key = f"{prefix}_{k}" if prefix else str(k)
                    walk(v, key)
                return
            if isinstance(node, list):
                for idx, v in enumerate(node):
                    key = f"{prefix}_{idx}" if prefix else str(idx)
                    walk(v, key)
                return
            if isinstance(node, (str, int, float, bool)):
                norm = OemClient._norm_key(prefix)
                text = OemClient._safe_text(node)
                if norm and text != "-":
                    out.setdefault(norm, text)

        walk(payload)
        return out

    @staticmethod
    def _pick_property_value(
        prop_map: dict[str, str],
        candidates: list[str],
        fallback_tokens: list[tuple[str, ...]] | None = None,
        prefer_ip_value: bool = False,
    ) -> str:
        for key in candidates:
            norm = OemClient._norm_key(key)
            val = prop_map.get(norm)
            if val:
                return val
        if fallback_tokens:
            fuzzy = OemClient._fuzzy_pick(prop_map, fallback_tokens, prefer_ip_value=prefer_ip_value)
            if fuzzy:
                return fuzzy
        return "-"

    @staticmethod
    def _fuzzy_pick(
        prop_map: dict[str, str],
        token_groups: list[tuple[str, ...]],
        prefer_ip_value: bool = False,
    ) -> str:
        for key, value in prop_map.items():
            k = key.lower()
            v = value.strip()
            if not v or v == "-":
                continue
            for group in token_groups:
                if all(token in k for token in group):
                    if prefer_ip_value and not OemClient._looks_like_ip(v):
                        continue
                    return v
        return "-"

    @staticmethod
    def _looks_like_ip(value: str) -> bool:
        return re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value.strip()) is not None

    @staticmethod
    def _norm_key(key: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", key.lower())

    @staticmethod
    def _safe_text(value: Any) -> str:
        text = str(value).strip()
        if not text:
            return "-"
        return " ".join(text.split())

    @staticmethod
    def _build_url(base_url: str, endpoint: str) -> str:
        """
        兼容两种 base_url:
        1) https://host:port
        2) https://host:port/em/api
        并兼容 endpoint 以 /em/api 或 / 开头。
        """
        base = base_url.rstrip("/")
        ep = endpoint if endpoint.startswith("/") else f"/{endpoint}"

        # base 已包含 /em/api 且 endpoint 也包含 /em/api 时，去重 endpoint 前缀。
        if base.lower().endswith("/em/api") and ep.lower().startswith("/em/api/"):
            ep = ep[len("/em/api") :]

        # 规范化 base 中连续的 /。
        split = urlsplit(base)
        normalized_base = f"{split.scheme}://{split.netloc}{split.path.rstrip('/')}"
        return f"{normalized_base}{ep}"

    def _fetch_events_from_incidents(
        self,
        base_url: str,
        auth: tuple[str, str],
        incident_events_endpoint: str,
        incidents: Any,
    ) -> list[dict[str, Any]]:
        incident_items = _extract_items(incidents)
        events: list[dict[str, Any]] = []
        for incident in incident_items[:5]:
            incident_id = incident.get("id")
            if not incident_id:
                continue
            endpoint = incident_events_endpoint.format(incidentId=incident_id)
            try:
                payload = self._get_json(
                    base_url=base_url,
                    endpoint=endpoint,
                    auth=auth,
                    params={"limit": 20},
                )
            except RuntimeError:
                continue
            for ev in _extract_items(payload):
                events.append(ev)
        return events


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    items = _extract_items(value)
    if items:
        return items
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def _extract_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        raw_items = value.get("items")
        if isinstance(raw_items, list):
            return [x for x in raw_items if isinstance(x, dict)]
    return []


def _extract_next_page_token(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    links = value.get("links")
    if not isinstance(links, dict):
        return None
    next_link = links.get("next")
    if not isinstance(next_link, dict):
        return None
    href = str(next_link.get("href", "")).strip()
    if not href:
        return None
    marker = "page="
    idx = href.find(marker)
    if idx < 0:
        return None
    token = href[idx + len(marker) :]
    amp = token.find("&")
    if amp >= 0:
        token = token[:amp]
    return token or None
