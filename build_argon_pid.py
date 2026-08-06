from __future__ import annotations
from math import cos, radians, sin
from pathlib import Path
from agentcad.models import AddSystemOperation, CreateDocumentRequest, SystemGroup, TransactionRequest
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry

BLUE = "#1d4ed8"
GREEN = "#15803d"
RED = "#b91c1c"
INK = "#111827"
SYS_SUPPLY = "sys_supply"
SYS_EXHAUST = "sys_exhaust"
SYS_CIRC = "sys_circ"
PROJECT = Path(__file__).resolve().parent
DB = PROJECT / "data" / "argon_pid.db"
OUT = PROJECT / "reports" / "argon_pid"
OUT.mkdir(parents=True, exist_ok=True)
_REG = None
operations = []
_placed = {}
_placed_junc = {}


def reg():
    global _REG
    if _REG is None:
        _REG = SymbolRegistry()
    return _REG


def P(x, y):
    return {"x": float(x), "y": float(y)}


def port_point(eid, port_id):
    info = _placed[eid]
    d = reg().get(info["key"])
    port = next(p for p in d.ports if p.id == port_id)
    sx = info["w"] / d.width
    sy = info["h"] / d.height
    lx = port.x * sx
    ly = port.y * sy
    cx = info["w"] / 2
    cy = info["h"] / 2
    a = radians(info["rot"])
    dx, dy = lx - cx, ly - cy
    rx = cx + dx * cos(a) - dy * sin(a)
    ry = cy + dx * sin(a) + dy * cos(a)
    return (info["x"] + rx, info["y"] + ry)


def J(eid, x, y, **kw):
    return add_junc(eid, x, y, **kw)


def add_sym(eid, key, x, y, w=None, h=None, rotation=0, system_id="system_default",
            label="", props=None, style=None):
    d = reg().get(key)
    ww = w or d.width
    hh = h or d.height
    _placed[eid] = {"key": key, "x": x, "y": y, "w": ww, "h": hh, "rot": rotation}
    base_style = {"stroke": INK, "fill": "none", "stroke_width": 1.5, "opacity": 1.0}
    if style:
        base_style.update(style)
    operations.append({"op": "add_element", "element": {
        "id": eid, "type": "symbol", "symbol_key": key, "position": P(x, y),
        "width": ww, "height": hh, "rotation": rotation, "label": label,
        "system_id": system_id, "properties": props or {}, "style": base_style,
    }})
    return eid


def add_junc(eid, x, y, system_id="system_default", label="", style=None):
    base_style = {"stroke": INK, "fill": INK, "stroke_width": 1.5, "opacity": 1.0}
    if style:
        base_style.update(style)
    operations.append({"op": "add_element", "element": {
        "id": eid, "type": "junction", "position": P(x, y), "radius": 4,
        "label": label, "system_id": system_id, "style": base_style,
    }})
    _placed_junc[eid] = (x, y)
    return eid


def add_text(eid, x, y, t, fs=13, anchor="middle", system_id="system_default", color=None):
    operations.append({"op": "add_element", "element": {
        "id": eid, "type": "text", "position": P(x, y), "text": t, "font_size": fs,
        "anchor": anchor, "system_id": system_id,
        "style": {"stroke": color or INK, "fill": color or INK, "opacity": 1.0},
    }})
    return eid


def _mk_conn(eid, src_ep, tgt_ep, pts, medium, tag, flow, arrow, system_id, style):
    base_style = {"stroke": INK, "fill": "none", "stroke_width": 1.5, "opacity": 1.0}
    if style:
        base_style.update(style)
    operations.append({"op": "add_element", "element": {
        "id": eid, "type": "connector", "points": pts, "source": src_ep, "target": tgt_ep,
        "routing": "manual", "process_tag": tag, "medium": medium,
        "flow_direction": flow, "arrow_position": arrow, "crossing_style": "none",
        "system_id": system_id, "style": base_style,
    }})
    return eid


def add_conn(eid, src_id, src_port, tgt_id, tgt_port, pts=None, **kw):
    sx, sy = port_point(src_id, src_port)
    tx, ty = port_point(tgt_id, tgt_port)
    pts = [P(sx, sy), P(tx, ty)] if pts is None else [P(p[0], p[1]) for p in pts]
    src_ep = {"element_id": src_id, "port_id": src_port, "point": P(sx, sy)}
    tgt_ep = {"element_id": tgt_id, "port_id": tgt_port, "point": P(tx, ty)}
    return _mk_conn(eid, src_ep, tgt_ep, pts, kw.get("medium", "argon"), kw.get("tag", ""),
                    kw.get("flow", "forward"), kw.get("arrow", "middle"),
                    kw.get("system_id", "system_default"), kw.get("style"))


def add_conn_junc(eid, src_id, src_port, jid, pts=None, **kw):
    sx, sy = port_point(src_id, src_port)
    jx, jy = _placed_junc[jid]
    pts = [P(sx, sy), P(jx, jy)] if pts is None else [P(p[0], p[1]) for p in pts]
    src_ep = {"element_id": src_id, "port_id": src_port, "point": P(sx, sy)}
    tgt_ep = {"element_id": jid, "port_id": "node", "point": P(jx, jy)}
    return _mk_conn(eid, src_ep, tgt_ep, pts, kw.get("medium", "argon"), kw.get("tag", ""),
                    kw.get("flow", "forward"), kw.get("arrow", "middle"),
                    kw.get("system_id", "system_default"), kw.get("style"))


def add_conn_jsrc(eid, jid, tgt_id, tgt_port, pts=None, **kw):
    jx, jy = _placed_junc[jid]
    tx, ty = port_point(tgt_id, tgt_port)
    pts = [P(jx, jy), P(tx, ty)] if pts is None else [P(p[0], p[1]) for p in pts]
    src_ep = {"element_id": jid, "port_id": "node", "point": P(jx, jy)}
    tgt_ep = {"element_id": tgt_id, "port_id": tgt_port, "point": P(tx, ty)}
    return _mk_conn(eid, src_ep, tgt_ep, pts, kw.get("medium", "argon"), kw.get("tag", ""),
                    kw.get("flow", "forward"), kw.get("arrow", "middle"),
                    kw.get("system_id", "system_default"), kw.get("style"))


def add_conn_jj(eid, j1, j2, pts=None, **kw):
    x1, y1 = _placed_junc[j1]
    x2, y2 = _placed_junc[j2]
    pts = [P(x1, y1), P(x2, y2)] if pts is None else [P(p[0], p[1]) for p in pts]
    src_ep = {"element_id": j1, "port_id": "node", "point": P(x1, y1)}
    tgt_ep = {"element_id": j2, "port_id": "node", "point": P(x2, y2)}
    return _mk_conn(eid, src_ep, tgt_ep, pts, kw.get("medium", "argon"), kw.get("tag", ""),
                    kw.get("flow", "forward"), kw.get("arrow", "middle"),
                    kw.get("system_id", "system_default"), kw.get("style"))


def main():
    store = SQLiteDocumentStore(DB)
    svc = DocumentService(store, reg())
    doc = svc.create_document(
        CreateDocumentRequest(name="氩气供气与循环系统 P&ID", width=3100, height=2600),
        source="llm",
    )
    did = doc.id
    svc.apply_transaction(
        did,
        TransactionRequest(
            expected_revision=doc.revision, label="add systems", source="llm",
            operations=[
                AddSystemOperation(op="add_system", system=SystemGroup(id=SYS_SUPPLY, name="供气回路（蓝）")).model_dump(),
                AddSystemOperation(op="add_system", system=SystemGroup(id=SYS_EXHAUST, name="尾气收集与气雾冷凝（绿）")).model_dump(),
                AddSystemOperation(op="add_system", system=SystemGroup(id=SYS_CIRC, name="气体循环回路（红）")).model_dump(),
            ],
        ),
    )
    build()
    doc = svc.get_document(did)
    result = svc.apply_transaction(
        did,
        TransactionRequest(
            expected_revision=doc.revision, label="argon supply exhaust circulation full P&ID",
            source="llm", operations=operations,
        ),
    )
    doc = result.document
    print("applied rev =", doc.revision, "elements =", len(doc.elements), "ops =", result.applied_operations)
    (OUT / "doc_id.txt").write_text(did, encoding="utf-8")
    from agentcad.svg import render_svg
    svg = render_svg(doc, reg())
    (OUT / "argon_pid.svg").write_text(svg, encoding="utf-8")
    print("wrote", OUT / "argon_pid.svg")


def build():
    add_annotations()
    build_supply_zone()
    build_exhaust_zone()
    build_circulation_zone()


def add_annotations():
    # master title
    add_text("t_title", 1100, 60, "氩气供气与循环系统 P&ID（闭式循环）", fs=26, system_id="system_default", color=INK)
    add_text("t_subtitle", 1100, 95, "供气回路（蓝）→ 尾气收集与气雾冷凝（绿）→ 气体循环回路（红）→ 回用至泵轴封", fs=14, system_id="system_default", color="#374151")
    # zone labels
    add_text("t_zone_supply", 80, 130, "一、供气回路（蓝色框）", fs=18, system_id=SYS_SUPPLY, color=BLUE)
    add_text("t_zone_exhaust", 80, 1335, "二、尾气收集与气雾冷凝（绿色框）", fs=18, system_id=SYS_EXHAUST, color=GREEN)
    add_text("t_zone_circ", 80, 2010, "三、气体循环回路（红色框）", fs=18, system_id=SYS_CIRC, color=RED)
    # zone boundary rectangles (thin colored frames)
    operations.append({"op": "add_element", "element": {
        "id": "box_supply", "type": "rectangle", "x": 30, "y": 110, "width": 3040, "height": 1180,
        "system_id": SYS_SUPPLY,
        "style": {"stroke": BLUE, "fill": "none", "stroke_width": 2.0, "opacity": 1.0, "dash": [16, 8]},
    }})
    operations.append({"op": "add_element", "element": {
        "id": "box_exhaust", "type": "rectangle", "x": 30, "y": 1330, "width": 3040, "height": 640,
        "system_id": SYS_EXHAUST,
        "style": {"stroke": GREEN, "fill": "none", "stroke_width": 2.0, "opacity": 1.0, "dash": [16, 8]},
    }})
    operations.append({"op": "add_element", "element": {
        "id": "box_circ", "type": "rectangle", "x": 30, "y": 2000, "width": 3040, "height": 570,
        "system_id": SYS_CIRC,
        "style": {"stroke": RED, "fill": "none", "stroke_width": 2.0, "opacity": 1.0, "dash": [16, 8]},
    }})


def build_supply_zone():
    """Zone 1 (blue): Ar station -> purifiers -> analyzers -> main pipe -> 8 cabinets -> users."""
    S = SYS_SUPPLY
    sb = {"stroke": BLUE}
    # Ar gas station (left boundary)
    add_sym("ar_station", "off_page_connector_in", 40, 280, system_id=S, style=sb)
    add_text("t_ar_station", 90, 250, "氩气站\n新鲜气源", fs=15, system_id=S, color=BLUE)
    # Purification cabinet with 3 purifiers (1 use 2 standby)
    pur_x = 240
    add_text("t_purcab", pur_x + 130, 150, "供气系统纯化柜\n（三组纯化器 1用2备）", fs=14, system_id=S, color=BLUE)
    add_sym("pur1", "cartridge_filter", pur_x, 200, system_id=S, label="", style=sb)        # 用
    add_sym("pur2", "cartridge_filter", pur_x, 360, system_id=S, label="", style=sb)        # 备
    add_sym("pur3", "cartridge_filter", pur_x, 520, system_id=S, label="", style=sb)        # 备
    add_text("t_pur1", pur_x + 40, 195, "1#", fs=11, system_id=S, color=BLUE)
    add_text("t_pur2", pur_x + 40, 355, "2#", fs=11, system_id=S, color=BLUE)
    add_text("t_pur3", pur_x + 40, 515, "3#", fs=11, system_id=S, color=BLUE)
    add_text("t_pur1u", pur_x - 70, 250, "用", fs=12, system_id=S, color=BLUE)
    add_text("t_pur2u", pur_x - 70, 410, "备", fs=12, system_id=S, color=BLUE)
    add_text("t_pur3u", pur_x - 70, 570, "备", fs=12, system_id=S, color=BLUE)
    # DN100 main pipe header y = 600
    Y = 600
    # header junctions along main pipe
    J("j_main_start", pur_x + 80, Y, system_id=S)          # after purifiers merge
    J("j_h2o", pur_x + 260, Y, system_id=S)                # water analyzer tap
    J("j_o2", pur_x + 380, Y, system_id=S)                 # oxygen analyzer tap
    # analyzers on main pipe
    add_sym("an_h2o", "analyzer_indicator", pur_x + 250, Y - 180, system_id=S, label="", style=sb)
    add_sym("an_o2", "analyzer_indicator", pur_x + 370, Y - 180, system_id=S, label="", style=sb)
    add_text("t_an_h2o", pur_x + 275, Y - 200, "水分析仪\nH₂O", fs=11, system_id=S, color=BLUE)
    add_text("t_an_o2", pur_x + 395, Y - 200, "氧分析仪\nO₂", fs=11, system_id=S, color=BLUE)
    # isolation valve on main pipe
    add_sym("iso_v", "gate_valve", pur_x + 520, Y - 25, system_id=S, label="", style=sb)
    add_text("t_iso_v", pur_x + 550, Y - 40, "隔离阀", fs=11, system_id=S, color=BLUE)
    J("j_branch", pur_x + 680, Y, system_id=S)             # branch point to 8 cabinets
    add_text("t_dn100", pur_x + 250, Y + 30, "DN100 母管", fs=12, system_id=S, color=BLUE)
    # main pipe segments: ar_station -> pur1 -> j_main_start ; pur2/pur3 standby merge
    add_conn("c_ar_pur1", "ar_station", "process", "pur1", "in",
             pts=[(140, 305), (180, 305), (180, 230), (pur_x, 230)], system_id=S, medium="argon",
             tag="L-Ar-101", style=sb)
    add_conn_junc("c_pur1_main", "pur1", "out", "j_main_start",
                  pts=[(pur_x + 80, 230), (pur_x + 80, Y)], system_id=S, medium="argon", tag="L-Ar-101", style=sb)
    # standby purifiers (2#/3#) merge into same DN100 header via standby branches
    add_conn_junc("c_pur2_main", "pur2", "out", "j_main_start",
                  pts=[(pur_x + 80, 415), (pur_x + 80, Y)], system_id=S, medium="argon", flow="none", style=sb)
    add_conn_junc("c_pur3_main", "pur3", "out", "j_main_start",
                  pts=[(pur_x + 80, 575), (pur_x + 80, Y)], system_id=S, medium="argon", flow="none", style=sb)
    # main header segments
    add_conn_jj("c_main_1", "j_main_start", "j_h2o", system_id=S, medium="argon", tag="L-Ar-101", style=sb)
    add_conn_jj("c_main_2", "j_h2o", "j_o2", system_id=S, medium="argon", tag="L-Ar-101", style=sb)
    add_conn_jsrc("c_o2_iso", "j_o2", "iso_v", "in", system_id=S, medium="argon", tag="L-Ar-101", style=sb)
    add_conn_junc("c_iso_br", "iso_v", "out", "j_branch", system_id=S, medium="argon", tag="L-Ar-101", style=sb)
    # analyzer branch taps (vertical)
    add_conn_junc("c_h2o_tap", "an_h2o", "process", "j_h2o",
                  system_id=S, medium="argon", flow="none", style=sb)
    add_conn_junc("c_o2_tap", "an_o2", "process", "j_o2",
                  system_id=S, medium="argon", flow="none", style=sb)
    # eight supply cabinets below the branch point
    cab_y = 760
    users = [
        ("cab1", 320, ["燃料盐循环泵A", "溢流罐A", "应急排盐罐A"]),
        ("cab2", 690, ["冷却盐循环泵A(×2)", "冷却盐充排罐A"]),
        ("cab3", 1010, ["燃料盐循环泵B", "溢流罐B", "应急排盐罐B"]),
        ("cab4", 1380, ["冷却盐循环泵B(×2)", "冷却盐充排罐B"]),
        ("cab5", 1700, ["燃料盐循环泵C", "溢流罐C", "应急排盐罐C"]),
        ("cab6", 2070, ["冷却盐循环泵C(×2)", "冷却盐充排罐C"]),
        ("cab7", 2390, ["增殖盐循环泵(×2)", "堆芯"]),
        ("cab8", 2780, ["熔盐取样装置", "气体加热及输送子系统", "其他"]),
    ]
    for i, (cid, cx, ulist) in enumerate(users, 1):
        add_sym(cid, "horizontal_vessel", cx, cab_y, system_id=S, label="", style=sb)
        add_text(f"t_{cid}", cx + 65, cab_y + 100, f"供气柜{i}", fs=12, system_id=S, color=BLUE)
        # branch from main header down to cabinet in port (left side)
        add_sym(f"{cid}_in_iso", "gate_valve", cx - 70, cab_y + 15, system_id=S, label="", style=sb)
        # vertical branch from main pipe at cabinet x
        J(f"j_{cid}", cx - 30, Y, system_id=S)
        add_conn_jj(f"c_main_{cid}", "j_branch", f"j_{cid}",
                    pts=[(pur_x + 680, Y), (cx - 30, Y)], system_id=S, medium="argon",
                    tag="DN80/50", style=sb)
        add_conn_jsrc(f"c_br_{cid}", f"j_{cid}", f"{cid}_in_iso", "in",
                      system_id=S, medium="argon", tag="DN80/50", style=sb)
        add_conn(f"c_iso_cab_{cid}", f"{cid}_in_iso", "out", cid, "in",
                 system_id=S, medium="argon", tag="DN80/50", style=sb)
        # downstream users: vertical stack below cabinet, each with PT + check valve
        # cabinet right outlet -> drop to a sub-header, then branch to each user
        sub_y0 = cab_y + 170
        step = 175
        J(f"j_{cid}_sub", cx + 65, sub_y0, system_id=S)
        add_conn_junc(f"c_cab_sub_{cid}", cid, "out", f"j_{cid}_sub", system_id=S, medium="argon", tag="DN50", style=sb)
        for k, uname in enumerate(ulist):
            uk = f"{cid}_u{k}"
            uy = sub_y0 + k * step
            is_pump = "泵" in uname
            # user equipment
            if is_pump:
                add_sym(uk, "positive_displacement_pump", cx + 120, uy, system_id=S, label="", style=sb)
            elif "取样" in uname:
                add_sym(uk, "horizontal_vessel", cx + 120, uy, system_id=S, label="", style=sb)
            else:
                add_sym(uk, "gas_tank", cx + 120, uy, system_id=S, label="", style=sb)
            add_text(f"t_{uk}", cx + 120 + 35, uy + 130, uname, fs=10, system_id=S, color=BLUE)
            # PT above the user branch line
            add_sym(f"{uk}_pt", "pressure_indicator", cx - 10, uy - 75, system_id=S, label="", style=sb)
            add_text(f"t_{uk}_pt", cx + 15, uy - 95, "PT", fs=10, system_id=S, color=BLUE)
            # check valve at user inlet (horizontal, on the branch to user)
            add_sym(f"{uk}_cv", "check_valve", cx + 20, uy + 12, system_id=S, label="", style=sb)
            add_text(f"t_{uk}_cv", cx + 60, uy + 75, "止回阀", fs=9, system_id=S, color=BLUE)
            # sub-header junction -> PT tap -> check valve -> user
            J(f"j_{uk}", cx + 65, uy + 12, system_id=S)
            add_conn_jj(f"c_sub_{uk}", f"j_{cid}_sub", f"j_{uk}",
                        pts=[(cx + 65, sub_y0), (cx + 65, uy + 12)], system_id=S, medium="argon", tag="DN50", style=sb)
            add_conn_jsrc(f"c_pt_{uk}", f"j_{uk}", f"{uk}_pt", "process", system_id=S, medium="argon", flow="none", style=sb)
            add_conn_jsrc(f"c_cv_{uk}", f"j_{uk}", f"{uk}_cv", "in", system_id=S, medium="argon", tag="DN50", style=sb)
            if is_pump:
                add_conn(f"c_cvu_{uk}", f"{uk}_cv", "out", uk, "suction", system_id=S, medium="argon", tag="DN50", style=sb)
            else:
                add_conn(f"c_cvu_{uk}", f"{uk}_cv", "out", uk, "in", system_id=S, medium="argon", tag="DN50", style=sb)


def build_exhaust_zone():
    """Zone 2 (green): pump seal purge gas -> mist condenser -> collection -> exhaust treatment OPC."""
    S = SYS_EXHAUST
    sg = {"stroke": GREEN}
    # purge gas seal exhaust junctions from fuel salt pumps A/B/C and breeding pump
    # placed in the band below supply cabinets and their stacked users
    seal_y = 1420
    J("j_seal_a", 320 + 120, seal_y, system_id=S)        # from fuel pump A
    J("j_seal_b", 1010 + 120, seal_y, system_id=S)       # from fuel pump B
    J("j_seal_c", 1700 + 120, seal_y, system_id=S)       # from fuel pump C
    J("j_seal_breed", 2390 + 120, seal_y, system_id=S)   # from breeding pump
    add_text("t_seal", 200, seal_y - 30, "泵轴封吹扫气（高温，携带裂变气体与盐雾）", fs=13, system_id=S, color=GREEN)
    # connect each pump discharge to its seal exhaust junction (purge gas)
    for cab_idx, jid in enumerate(["j_seal_a", "j_seal_b", "j_seal_c"]):
        pump_id = ["cab1", "cab3", "cab5"][cab_idx] + "_u0"
        add_conn_junc(f"c_seal_{cab_idx}", pump_id, "discharge", jid,
                      system_id=S, medium="purge_gas", tag="L-PG-201", style=sg)
    add_conn_junc("c_seal_breed", "cab7_u0", "discharge", "j_seal_breed",
                  system_id=S, medium="purge_gas", tag="L-PG-201", style=sg)
    # merge seal gas into a header leading to mist condenser
    J("j_seal_merge", 1300, seal_y, system_id=S)
    add_conn_jj("c_sm_a", "j_seal_a", "j_seal_merge", system_id=S, medium="purge_gas", tag="L-PG-201", style=sg)
    add_conn_jj("c_sm_b", "j_seal_b", "j_seal_merge", system_id=S, medium="purge_gas", tag="L-PG-201", style=sg)
    add_conn_jj("c_sm_c", "j_seal_c", "j_seal_merge", system_id=S, medium="purge_gas", tag="L-PG-201", style=sg)
    add_conn_jj("c_sm_d", "j_seal_breed", "j_seal_merge", system_id=S, medium="purge_gas", tag="L-PG-201", style=sg)
    # mist condenser (shell-and-tube): process side purge gas, utility side cooling air
    cond_x, cond_y = 1700, 1560
    add_sym("mist_cond", "heat_exchanger_horizontal_shell", cond_x, cond_y, system_id=S, label="", style=sg)
    add_text("t_mist_cond", cond_x + 75, cond_y - 25, "气雾冷凝器\n(管壳式换热)", fs=13, system_id=S, color=GREEN)
    add_text("t_cond50", cond_x + 75, cond_y + 105, "冷却至 <50°C", fs=11, system_id=S, color=GREEN)
    # purge gas into tube_in, out tube_out (cooled)
    add_conn_jsrc("c_merg_cond", "j_seal_merge", "mist_cond", "tube_in",
                  pts=[(1300, seal_y), (1300, cond_y + 28), (cond_x, cond_y + 28)], system_id=S,
                  medium="purge_gas", tag="L-PG-201", style=sg)
    # cooling air side: PT + TF on air inlet/outlet
    air_y = cond_y + 200
    J("j_air_in", cond_x + 200, air_y, system_id=S)
    J("j_air_out", cond_x - 60, air_y, system_id=S)
    add_sym("air_pt", "pressure_indicator", cond_x + 250, air_y - 110, system_id=S, label="", style=sg)
    add_sym("air_tf", "temperature_indicator", cond_x + 320, air_y - 110, system_id=S, label="", style=sg)
    add_text("t_air_pt", cond_x + 275, air_y - 130, "PT", fs=10, system_id=S, color=GREEN)
    add_text("t_air_tf", cond_x + 345, air_y - 130, "TF", fs=10, system_id=S, color=GREEN)
    add_text("t_air", cond_x + 80, air_y + 30, "冷却空气", fs=11, system_id=S, color=GREEN)
    # air path: j_air_in -> utility_in (shell_in), utility_out (shell_out) -> j_air_out
    add_conn_jsrc("c_air_in", "j_air_in", "mist_cond", "shell_in", system_id=S, medium="cooling_air", tag="L-AIR-201", style=sg)
    add_conn_junc("c_air_out", "mist_cond", "shell_out", "j_air_out", system_id=S, medium="cooling_air", tag="L-AIR-201", flow="reverse", style=sg)
    add_conn_junc("c_air_pt_t", "air_pt", "process", "j_air_in", system_id=S, medium="cooling_air", flow="none", style=sg)
    add_conn_junc("c_air_tf_t", "air_tf", "process", "j_air_out", system_id=S, medium="cooling_air", flow="none", style=sg)
    add_text("t_air_in", cond_x + 250, air_y + 30, "空气进气口", fs=10, system_id=S, color=GREEN)
    add_text("t_air_out", cond_x - 120, air_y + 30, "空气出气口", fs=10, system_id=S, color=GREEN)
    # collection tank at bottom (condensed salt/oil mist)
    coll_x, coll_y = cond_x + 30, cond_y + 260
    add_sym("coll_tank", "drain_vessel", coll_x, coll_y, system_id=S, label="", style=sg)
    add_text("t_coll", coll_x + 60, coll_y + 90, "集液槽\n(盐雾/油雾冷凝液)", fs=11, system_id=S, color=GREEN)
    add_conn("c_cond_drain", "mist_cond", "shell_out", "coll_tank", "top",
             system_id=S, medium="liquid", tag="L-DRN-201", flow="reverse", style=sg)
    # cooled gas from condenser top outlet -> exhaust treatment system OPC (DN50)
    # exhaust treatment system as off-page connector out
    et_x, et_y = 2400, cond_y
    add_sym("exhaust_treat", "off_page_connector_out", et_x, et_y, system_id=S, label="", style=sg)
    add_text("t_exhaust", et_x + 50, et_y - 30, "尾气处理系统\n(DN50)", fs=13, system_id=S, color=GREEN)
    add_conn("c_cond_et", "mist_cond", "tube_out", "exhaust_treat", "process",
             pts=[(cond_x + 150, cond_y + 28), (et_x, et_y + 25)], system_id=S,
             medium="purge_gas", tag="L-PG-201 DN50", style=sg)


def build_circulation_zone():
    """Zone 3 (red): exhaust-treatment outlet -> booster pumps -> buffer tanks ->
    circulation purifiers -> analyzers -> dedicated supply cabinet -> return to pump seals."""
    S = SYS_CIRC
    sr = {"stroke": RED}
    # start: purified gas from exhaust treatment enters circulation (off-page connector in)
    start_x, start_y = 200, 2150
    add_sym("circ_in", "off_page_connector_in", start_x, start_y, system_id=S, label="", style=sr)
    add_text("t_circ_in", start_x + 50, start_y - 30, "尾气处理系统出口\n净化气体", fs=12, system_id=S, color=RED)
    Y = start_y + 25  # circulation main line y
    # booster pumps (1 use 1 standby, upper/lower parallel)
    bp_x = 420
    add_text("t_bp", bp_x + 45, start_y - 60, "增压泵\n(1用1备 并联)", fs=12, system_id=S, color=RED)
    add_sym("bp1", "positive_displacement_pump", bp_x, start_y - 90, system_id=S, label="", style=sr)   # 用 (upper)
    add_sym("bp2", "positive_displacement_pump", bp_x, start_y + 110, system_id=S, label="", style=sr)  # 备 (lower)
    add_text("t_bp1u", bp_x - 50, start_y - 55, "用", fs=11, system_id=S, color=RED)
    add_text("t_bp2u", bp_x - 50, start_y + 145, "备", fs=11, system_id=S, color=RED)
    J("j_bp_in", bp_x - 40, Y, system_id=S)
    J("j_bp_out", bp_x + 140, Y, system_id=S)
    # PT at booster pump outlet
    add_sym("bp_pt", "pressure_indicator", bp_x + 160, Y - 120, system_id=S, label="", style=sr)
    add_text("t_bp_pt", bp_x + 185, Y - 140, "PT", fs=10, system_id=S, color=RED)
    # circ_in -> j_bp_in ; j_bp_in -> bp1/bp2 ; bp1/bp2 -> j_bp_out
    add_conn("c_in_bp", "circ_in", "process", "bp1", "suction",
             pts=[(start_x + 100, Y), (bp_x - 40, Y)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_jsrc("c_jbp_bp1", "j_bp_in", "bp1", "suction",
                  pts=[(bp_x - 40, Y), (bp_x - 40, start_y - 55), (bp_x, start_y - 55)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_jsrc("c_jbp_bp2", "j_bp_in", "bp2", "suction",
                  pts=[(bp_x - 40, Y), (bp_x - 40, start_y + 145), (bp_x, start_y + 145)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_junc("c_bp1_jbp", "bp1", "discharge", "j_bp_out",
                  pts=[(bp_x + 48, start_y - 90), (bp_x + 140, start_y - 90), (bp_x + 140, Y)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_junc("c_bp2_jbp", "bp2", "discharge", "j_bp_out",
                  pts=[(bp_x + 48, start_y + 110), (bp_x + 140, start_y + 110), (bp_x + 140, Y)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_junc("c_bp_pt_t", "bp_pt", "process", "j_bp_out", system_id=S, medium="argon", flow="none", style=sr)
    # buffer tanks (1 use 1 standby, upper/lower parallel)
    bt_x = 760
    add_text("t_bt", bt_x + 45, start_y - 60, "缓冲罐\n(1用1备 并联)", fs=12, system_id=S, color=RED)
    add_sym("bt1", "gas_tank", bt_x, start_y - 120, system_id=S, label="", style=sr)   # 用 (upper)
    add_sym("bt2", "gas_tank", bt_x, start_y + 120, system_id=S, label="", style=sr)   # 备 (lower)
    add_sym("bt1_pi", "pressure_indicator", bt_x + 110, start_y - 100, system_id=S, label="", style=sr)
    add_sym("bt2_pi", "pressure_indicator", bt_x + 110, start_y + 160, system_id=S, label="", style=sr)
    add_text("t_bt1u", bt_x - 50, start_y - 70, "用", fs=11, system_id=S, color=RED)
    add_text("t_bt2u", bt_x - 50, start_y + 170, "备", fs=11, system_id=S, color=RED)
    add_text("t_bt1pi", bt_x + 135, start_y - 120, "PI", fs=10, system_id=S, color=RED)
    add_text("t_bt2pi", bt_x + 135, start_y + 140, "PI", fs=11, system_id=S, color=RED)
    J("j_bt_in", bt_x - 40, Y, system_id=S)
    J("j_bt_out", bt_x + 130, Y, system_id=S)
    add_conn_jj("c_jbp_jbt", "j_bp_out", "j_bt_in", system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_jsrc("c_jbt_bt1", "j_bt_in", "bt1", "in",
                  pts=[(bt_x - 40, Y), (bt_x - 40, start_y - 50), (bt_x, start_y - 50)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_jsrc("c_jbt_bt2", "j_bt_in", "bt2", "in",
                  pts=[(bt_x - 40, Y), (bt_x - 40, start_y + 190), (bt_x, start_y + 190)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_junc("c_bt1_jbt", "bt1", "out", "j_bt_out",
                  pts=[(bt_x + 90, start_y - 50), (bt_x + 130, start_y - 50), (bt_x + 130, Y)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_junc("c_bt2_jbt", "bt2", "out", "j_bt_out",
                  pts=[(bt_x + 90, start_y + 190), (bt_x + 130, start_y + 190), (bt_x + 130, Y)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn("c_bt1pi_t", "bt1_pi", "process", "bt1", "top", system_id=S, medium="argon", flow="none", style=sr)
    add_conn("c_bt2pi_t", "bt2_pi", "process", "bt2", "top", system_id=S, medium="argon", flow="none", style=sr)
    # circulation purifiers (1 use 1 standby, upper/lower parallel)
    cp_x = 1100
    add_text("t_cp", cp_x + 40, start_y - 60, "循环回路纯化器\n(1用1备 并联)", fs=12, system_id=S, color=RED)
    add_sym("cp1", "cartridge_filter", cp_x, start_y - 90, system_id=S, label="", style=sr)   # 用
    add_sym("cp2", "cartridge_filter", cp_x, start_y + 110, system_id=S, label="", style=sr)  # 备
    add_text("t_cp1u", cp_x - 60, start_y - 55, "用", fs=11, system_id=S, color=RED)
    add_text("t_cp2u", cp_x - 60, start_y + 145, "备", fs=11, system_id=S, color=RED)
    J("j_cp_in", cp_x - 40, Y, system_id=S)
    J("j_cp_out", cp_x + 120, Y, system_id=S)
    add_conn_jj("c_jbt_jcp", "j_bt_out", "j_cp_in", system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_jsrc("c_jcp_cp1", "j_cp_in", "cp1", "in",
                  pts=[(cp_x - 40, Y), (cp_x - 40, start_y - 55), (cp_x, start_y - 55)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_jsrc("c_jcp_cp2", "j_cp_in", "cp2", "in",
                  pts=[(cp_x - 40, Y), (cp_x - 40, start_y + 145), (cp_x, start_y + 145)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_junc("c_cp1_jcp", "cp1", "out", "j_cp_out",
                  pts=[(cp_x + 80, start_y - 55), (cp_x + 120, start_y - 55), (cp_x + 120, Y)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_conn_junc("c_cp2_jcp", "cp2", "out", "j_cp_out",
                  pts=[(cp_x + 80, start_y + 145), (cp_x + 120, start_y + 145), (cp_x + 120, Y)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    # independent H2O / O2 analyzers after purification
    J("j_circ_an", cp_x + 260, Y, system_id=S)
    add_conn_jj("c_jcp_an", "j_cp_out", "j_circ_an", system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_sym("circ_h2o", "analyzer_indicator", cp_x + 250, Y - 180, system_id=S, label="", style=sr)
    add_sym("circ_o2", "analyzer_indicator", cp_x + 330, Y - 180, system_id=S, label="", style=sr)
    add_text("t_circ_h2o", cp_x + 275, Y - 200, "水分析仪", fs=10, system_id=S, color=RED)
    add_text("t_circ_o2", cp_x + 355, Y - 200, "氧分析仪", fs=10, system_id=S, color=RED)
    add_conn_junc("c_circ_h2o_t", "circ_h2o", "process", "j_circ_an", system_id=S, medium="argon", flow="none", style=sr)
    add_conn_junc("c_circ_o2_t", "circ_o2", "process", "j_circ_an", system_id=S, medium="argon", flow="none", style=sr)
    # dedicated supply cabinet
    sc_x = 1700
    add_sym("circ_cab", "horizontal_vessel", sc_x, Y - 40, system_id=S, label="", style=sr)
    add_text("t_circ_cab", sc_x + 65, Y + 60, "专用供气柜", fs=13, system_id=S, color=RED)
    add_conn_jsrc("c_an_cab", "j_circ_an", "circ_cab", "in",
                  pts=[(cp_x + 260, Y), (sc_x, Y)], system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    # return path to fuel salt pumps & breeding pump seals at 0.5 MPa (red box bottom)
    J("j_ret", sc_x + 240, Y, system_id=S)
    add_conn_junc("c_cab_ret", "circ_cab", "out", "j_ret", system_id=S, medium="argon", tag="L-Ar-301", style=sr)
    add_text("t_ret", sc_x + 200, Y - 60, "回用气体 0.5MPa", fs=12, system_id=S, color=RED)
    add_text("t_ret2", sc_x + 200, Y - 40, "（循环回用路径）", fs=11, system_id=S, color=RED)
    # return connectors to pump seal purge gas inlets (fuel salt pumps A/B/C & breeding pump)
    ret_y = 2050
    add_sym("ret_a", "off_page_connector_out", 320 + 120, ret_y, system_id=S, label="", style=sr)
    add_sym("ret_b", "off_page_connector_out", 1010 + 120, ret_y, system_id=S, label="", style=sr)
    add_sym("ret_c", "off_page_connector_out", 1700 + 120, ret_y, system_id=S, label="", style=sr)
    add_sym("ret_breed", "off_page_connector_out", 2390 + 120, ret_y, system_id=S, label="", style=sr)
    for rid, rl in [("ret_a", "至燃料盐泵A吹扫气入口"), ("ret_b", "至燃料盐泵B吹扫气入口"),
                    ("ret_c", "至燃料盐泵C吹扫气入口"), ("ret_breed", "至增殖盐泵吹扫气入口")]:
        rx, _ry = _placed[rid]["x"], _placed[rid]["y"]
        add_text(f"t_{rid}", rx + 50, _ry - 30, rl, fs=10, system_id=S, color=RED)
        add_conn_jsrc(f"c_{rid}", "j_ret", rid, "process",
                      pts=[(sc_x + 240, Y), (sc_x + 240, ret_y + 25), (rx, ret_y + 25)], system_id=S,
                      medium="argon", tag="L-Ar-301 0.5MPa", style=sr)


if __name__ == "__main__":
    main()
