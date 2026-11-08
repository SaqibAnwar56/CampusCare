"""Tiny diagram kit: one specification -> editable Draw.io XML + high-resolution PNG.
Used by make_uml.py so that the PNGs in the report and the .drawio source files always match."""
import math
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon, Rectangle

NAVY, BLUE, LIGHT, GREY = "#0b1f3a", "#2563eb", "#e8f0fe", "#64748b"


class Diagram:
    def __init__(self, title, w, h):
        self.title, self.w, self.h = title, w, h
        self.nodes, self.edges, self.extra = {}, [], []
        self.n = 1
        self.fscale = 1.0

    def F(self, v):
        return v * self.fscale

    def _id(self):
        self.n += 1
        return f"c{self.n}"

    # ---- nodes -------------------------------------------------------------------------------
    def box(self, key, x, y, w, h, text="", fill="#ffffff", stroke=NAVY, bold=False, dashed=False, rounded=True, fs=11,
            shape="rect"):
        self.nodes[key] = dict(kind=shape, x=x, y=y, w=w, h=h, text=text, fill=fill, stroke=stroke, bold=bold,
                               dashed=dashed, rounded=rounded, fs=fs, id=self._id())

    def ellipse(self, key, x, y, w, h, text, fill=LIGHT, fs=10.5):
        self.box(key, x, y, w, h, text, fill=fill, stroke=BLUE, fs=fs, shape="ellipse")

    def actor(self, key, cx, y, label):
        self.nodes[key] = dict(kind="actor", x=cx - 20, y=y, w=40, h=84, text=label, id=self._id(), fs=11)

    def cls(self, key, x, y, name, attrs, methods, stereo=None, w=None, fill="#ffffff", header=LIGHT, fs=9.3):
        lines = [name] + attrs + methods + ([stereo] if stereo else [])
        w = w or max(150, int(max(len(s) for s in lines) * 7.3) + 22)
        lh = 15.5
        h_head = 34 if stereo else 24
        methods = [m for m in (methods or []) if m]
        h = h_head + (len(attrs) * lh + 12 if attrs else 0) + (len(methods) * lh + 12 if methods else 0)
        if not attrs and not methods:
            h += 10
        self.nodes[key] = dict(kind="class", x=x, y=y, w=w, h=h, name=name, attrs=attrs, methods=methods, stereo=stereo,
                               fill=fill, header=header, h_head=h_head, lh=lh, id=self._id(), fs=fs)

    def lifeline(self, key, cx, y, w, h, label, fill=LIGHT):
        self.nodes[key] = dict(kind="lifeline", x=cx - w / 2, y=y, w=w, h=46, text=label, fill=fill, bottom=y + h,
                               id=self._id(), fs=11)

    def frame(self, x, y, w, h, label, divider=None, divider_text=""):
        self.extra.append(dict(kind="frame", x=x, y=y, w=w, h=h, label=label, divider=divider,
                               divider_text=divider_text, id=self._id()))

    def note(self, x, y, w, h, text, fs=9.5):
        self.extra.append(dict(kind="note", x=x, y=y, w=w, h=h, text=text, fs=fs, id=self._id()))

    def label(self, x, y, text, fs=11, bold=False, color=NAVY, align="left"):
        self.extra.append(dict(kind="label", x=x, y=y, text=text, fs=fs, bold=bold, color=color, align=align,
                               id=self._id()))

    def region(self, x, y, w, h, text, fill="#f8fafc", stroke="#94a3b8"):
        self.extra.insert(0, dict(kind="region", x=x, y=y, w=w, h=h, text=text, fill=fill, stroke=stroke, id=self._id()))

    # ---- edges -------------------------------------------------------------------------------
    def edge(self, a, b, label="", kind="assoc", pts=(), a_lbl="", b_lbl="", lbl_off=(0, -9)):
        self.edges.append(dict(a=a, b=b, label=label, kind=kind, pts=list(pts), a_lbl=a_lbl, b_lbl=b_lbl,
                               lbl_off=lbl_off, id=self._id()))

    def msg(self, x1, x2, y, label, dashed=False, selfcall=False):
        self.edges.append(dict(kind="msg", x1=x1, x2=x2, y=y, label=label, dashed=dashed, selfcall=selfcall,
                               id=self._id()))

    # ---- geometry ----------------------------------------------------------------------------
    @staticmethod
    def _center(n):
        return n["x"] + n["w"] / 2, n["y"] + n["h"] / 2

    def _clip(self, n, toward):
        """Point on node border in the direction of `toward`."""
        cx, cy = self._center(n)
        dx, dy = toward[0] - cx, toward[1] - cy
        if dx == 0 and dy == 0:
            return cx, cy
        if n["kind"] == "ellipse":
            a, b = n["w"] / 2, n["h"] / 2
            t = 1 / math.sqrt((dx / a) ** 2 + (dy / b) ** 2)
            return cx + dx * t, cy + dy * t
        if n["kind"] == "actor":
            return cx, cy
        hw, hh = n["w"] / 2, n["h"] / 2
        t = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
        return cx + dx * t, cy + dy * t

    def _route(self, e):
        a, b = self.nodes[e["a"]], self.nodes[e["b"]]
        pts = e["pts"]
        ca, cb = self._center(a), self._center(b)
        p0 = self._clip(a, pts[0] if pts else cb)
        p1 = self._clip(b, pts[-1] if pts else ca)
        return [p0] + list(pts) + [p1]

    # ---- PNG ---------------------------------------------------------------------------------
    def png(self, path, dpi=170):
        fig = plt.figure(figsize=(self.w / 100, self.h / 100), dpi=dpi)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, self.w); ax.set_ylim(self.h, 0); ax.axis("off")
        for x in self.extra:
            if x["kind"] == "region":
                ax.add_patch(Rectangle((x["x"], x["y"]), x["w"], x["h"], fc=x["fill"], ec=x["stroke"], lw=1.3, ls="--"))
                ax.text(x["x"] + 12, x["y"] + 16, x["text"], fontsize=self.F(11), fontweight="bold", color=GREY, va="center")
        for n in self.nodes.values():
            self._draw_node(ax, n)
        for x in self.extra:
            self._draw_extra(ax, x)
        for e in self.edges:
            self._draw_edge(ax, e)
        fig.savefig(path, dpi=dpi, facecolor="white")
        plt.close(fig)

    def _draw_node(self, ax, n):
        k = n["kind"]
        if k in ("rect", "ellipse"):
            if k == "ellipse":
                ax.add_patch(Ellipse((n["x"] + n["w"] / 2, n["y"] + n["h"] / 2), n["w"], n["h"], fc=n["fill"], ec=n["stroke"], lw=1.4))
            else:
                ax.add_patch(FancyBboxPatch((n["x"], n["y"]), n["w"], n["h"], boxstyle="round,pad=0,rounding_size=%d" % (8 if n["rounded"] else 0),
                                            fc=n["fill"], ec=n["stroke"], lw=1.5, ls="--" if n["dashed"] else "-"))
            ax.text(n["x"] + n["w"] / 2, n["y"] + n["h"] / 2, n["text"], ha="center", va="center", fontsize=self.F(n["fs"]),
                    fontweight="bold" if n["bold"] else "normal", color=NAVY, linespacing=1.25)
        elif k == "actor":
            cx, y = n["x"] + n["w"] / 2, n["y"]
            ax.add_patch(Ellipse((cx, y + 9), 18, 18, fc="white", ec=NAVY, lw=1.6))
            ax.plot([cx, cx], [y + 18, y + 48], color=NAVY, lw=1.6)
            ax.plot([cx - 17, cx + 17], [y + 28, y + 28], color=NAVY, lw=1.6)
            ax.plot([cx, cx - 14], [y + 48, y + 70], color=NAVY, lw=1.6)
            ax.plot([cx, cx + 14], [y + 48, y + 70], color=NAVY, lw=1.6)
            ax.text(cx, y + 80, n["text"], ha="center", va="top", fontsize=self.F(n["fs"]), fontweight="bold", color=NAVY, linespacing=1.2)
        elif k == "class":
            ax.add_patch(Rectangle((n["x"], n["y"]), n["w"], n["h"], fc=n["fill"], ec=NAVY, lw=1.4))
            ax.add_patch(Rectangle((n["x"], n["y"]), n["w"], n["h_head"], fc=n["header"], ec=NAVY, lw=1.4))
            cy = n["y"] + n["h_head"] / 2
            if n["stereo"]:
                ax.text(n["x"] + n["w"] / 2, n["y"] + 11, n["stereo"], ha="center", va="center", fontsize=self.F(8.3), style="italic", color=GREY)
                cy = n["y"] + 24
            ax.text(n["x"] + n["w"] / 2, cy, n["name"], ha="center", va="center", fontsize=self.F(10.5), fontweight="bold", color=NAVY)
            y = n["y"] + n["h_head"] + 6
            for a in n["attrs"]:
                ax.text(n["x"] + 8, y + n["lh"] / 2, a, ha="left", va="center", fontsize=self.F(n["fs"]), family="DejaVu Sans Mono", color="#111827")
                y += n["lh"]
            if n["attrs"]:
                y += 6
            if n["attrs"] and n["methods"]:
                ax.plot([n["x"], n["x"] + n["w"]], [y - 1, y - 1], color=NAVY, lw=1.2)
                y += 5
            for m in n["methods"] or []:
                ax.text(n["x"] + 8, y + n["lh"] / 2, m, ha="left", va="center", fontsize=self.F(n["fs"]), family="DejaVu Sans Mono", color="#111827")
                y += n["lh"]
        elif k == "lifeline":
            ax.add_patch(FancyBboxPatch((n["x"], n["y"]), n["w"], n["h"], boxstyle="round,pad=0,rounding_size=6", fc=n["fill"], ec=NAVY, lw=1.5))
            ax.text(n["x"] + n["w"] / 2, n["y"] + n["h"] / 2, n["text"], ha="center", va="center", fontsize=self.F(n["fs"]), fontweight="bold", color=NAVY, linespacing=1.2)
            cx = n["x"] + n["w"] / 2
            ax.plot([cx, cx], [n["y"] + n["h"], n["bottom"]], color=GREY, lw=1.2, ls=(0, (5, 4)))

    def _draw_extra(self, ax, x):
        if x["kind"] == "frame":
            ax.add_patch(Rectangle((x["x"], x["y"]), x["w"], x["h"], fc="none", ec="#475569", lw=1.3))
            ax.add_patch(Polygon([(x["x"], x["y"]), (x["x"] + 118, x["y"]), (x["x"] + 118, x["y"] + 14), (x["x"] + 106, x["y"] + 26), (x["x"], x["y"] + 26)], fc="#e2e8f0", ec="#475569", lw=1.2))
            ax.text(x["x"] + 8, x["y"] + 13, x["label"], fontsize=self.F(9.5), fontweight="bold", va="center", color=NAVY)
            if x["divider"]:
                ax.plot([x["x"], x["x"] + x["w"]], [x["divider"]] * 2, color="#475569", lw=1.1, ls=(0, (5, 4)))
                ax.text(x["x"] + 10, x["divider"] + 12, x["divider_text"], fontsize=self.F(9.2), color="#475569", va="center")
        elif x["kind"] == "note":
            ax.add_patch(Polygon([(x["x"], x["y"]), (x["x"] + x["w"] - 14, x["y"]), (x["x"] + x["w"], x["y"] + 14), (x["x"] + x["w"], x["y"] + x["h"]), (x["x"], x["y"] + x["h"])], fc="#fffbeb", ec="#d97706", lw=1.1))
            ax.text(x["x"] + 8, x["y"] + 8, x["text"], fontsize=self.F(x["fs"]), va="top", ha="left", color="#78350f", linespacing=1.3)
        elif x["kind"] == "label":
            ax.text(x["x"], x["y"], x["text"], fontsize=self.F(x["fs"]), fontweight="bold" if x["bold"] else "normal", color=x["color"], ha=x["align"], va="center")

    def _draw_edge(self, ax, e):
        k = e["kind"]
        if k == "msg":
            x1, x2, y = e["x1"], e["x2"], e["y"]
            ls = (0, (5, 3)) if e["dashed"] else "-"
            if e["selfcall"]:
                xs, ys = [x1, x1 + 42, x1 + 42, x1 + 4], [y, y, y + 20, y + 20]
                ax.plot(xs, ys, color=NAVY, lw=1.3, ls=ls)
                self._arrowhead(ax, (x1 + 4, y + 20), (x1 + 42, y + 20), filled=True)
                ax.text(x1 + 50, y + 8, e["label"], fontsize=self.F(9.3), va="center", color=NAVY)
            else:
                ax.plot([x1, x2], [y, y], color=NAVY, lw=1.3, ls=ls)
                self._arrowhead(ax, (x2, y), (x1, y), filled=not e["dashed"])
                ax.text((x1 + x2) / 2, y - 7, e["label"], fontsize=self.F(9.3), ha="center", va="bottom", color=NAVY)
            return
        pts = self._route(e)
        k = e["kind"]
        ls = (0, (5, 3)) if k in ("dep", "include", "extend") else "-"
        color = NAVY if k != "dep" else GREY
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color, lw=1.3, ls=ls)
        if k in ("arrow", "dep", "include", "extend", "seq"):
            self._arrowhead(ax, pts[-1], pts[-2], filled=False if k in ("dep", "include", "extend") else True)
        elif k == "inherit":
            self._triangle(ax, pts[-1], pts[-2])
        elif k == "compose":
            self._diamond(ax, pts[0], pts[1])
        mx, my = (pts[len(pts) // 2 - 1][0] + pts[len(pts) // 2][0]) / 2, (pts[len(pts) // 2 - 1][1] + pts[len(pts) // 2][1]) / 2
        if e["label"]:
            ax.text(mx + e["lbl_off"][0], my + e["lbl_off"][1], e["label"], fontsize=self.F(9), ha="center", va="center", color=color, style="italic" if k in ("include", "extend") else "normal",
                    bbox=dict(fc="white", ec="none", pad=1.2, alpha=.9))
        if e["a_lbl"]:
            self._endlabel(ax, pts[0], pts[1], e["a_lbl"])
        if e["b_lbl"]:
            self._endlabel(ax, pts[-1], pts[-2], e["b_lbl"])

    def _endlabel(self, ax, p, q, text):
        dx, dy = q[0] - p[0], q[1] - p[1]
        d = math.hypot(dx, dy) or 1
        ux, uy = dx / d, dy / d
        ax.text(p[0] + ux * 18 - uy * 11, p[1] + uy * 18 + ux * 11, text, fontsize=self.F(9.5), ha="center", va="center", color="#b45309", fontweight="bold")

    @staticmethod
    def _arrowhead(ax, tip, frm, filled=True, size=11):
        dx, dy = tip[0] - frm[0], tip[1] - frm[1]
        d = math.hypot(dx, dy) or 1
        ux, uy = dx / d, dy / d
        l = (tip[0] - ux * size - uy * size * .42, tip[1] - uy * size + ux * size * .42)
        r = (tip[0] - ux * size + uy * size * .42, tip[1] - uy * size - ux * size * .42)
        if filled:
            ax.add_patch(Polygon([tip, l, r], fc=NAVY, ec=NAVY, lw=1))
        else:
            ax.plot([l[0], tip[0], r[0]], [l[1], tip[1], r[1]], color=NAVY, lw=1.3)

    @staticmethod
    def _triangle(ax, tip, frm, size=14):
        dx, dy = tip[0] - frm[0], tip[1] - frm[1]
        d = math.hypot(dx, dy) or 1
        ux, uy = dx / d, dy / d
        l = (tip[0] - ux * size - uy * size * .55, tip[1] - uy * size + ux * size * .55)
        r = (tip[0] - ux * size + uy * size * .55, tip[1] - uy * size - ux * size * .55)
        ax.add_patch(Polygon([tip, l, r], fc="white", ec=NAVY, lw=1.3))

    @staticmethod
    def _diamond(ax, tip, toward, size=14):
        dx, dy = toward[0] - tip[0], toward[1] - tip[1]
        d = math.hypot(dx, dy) or 1
        ux, uy = dx / d, dy / d
        mid = (tip[0] + ux * size, tip[1] + uy * size)
        far = (tip[0] + ux * size * 2, tip[1] + uy * size * 2)
        l = (mid[0] - uy * size * .5, mid[1] + ux * size * .5)
        r = (mid[0] + uy * size * .5, mid[1] - ux * size * .5)
        ax.add_patch(Polygon([tip, l, far, r], fc=NAVY, ec=NAVY, lw=1))

    # ---- Draw.io -----------------------------------------------------------------------------
    def drawio(self, path):
        cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']

        def geo(x, y, w, h):
            return f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" as="geometry"/>'

        def vcell(i, value, style, x, y, w, h):
            cells.append(f'<mxCell id="{i}" value="{escape(value, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="1">{geo(x, y, w, h)}</mxCell>')

        for x in self.extra:
            if x["kind"] == "region":
                vcell(x["id"], x["text"], "rounded=0;whiteSpace=wrap;html=1;dashed=1;fillColor=#f8fafc;strokeColor=#94a3b8;verticalAlign=top;align=left;spacingLeft=10;fontStyle=1;fontColor=#64748b;", x["x"], x["y"], x["w"], x["h"])
        for n in self.nodes.values():
            k = n["kind"]
            if k == "rect":
                st = f'rounded={1 if n["rounded"] else 0};whiteSpace=wrap;html=1;fillColor={n["fill"]};strokeColor={n["stroke"]};fontColor={NAVY};fontSize={int(n["fs"] + 1)};' + ("fontStyle=1;" if n["bold"] else "") + ("dashed=1;" if n["dashed"] else "")
                vcell(n["id"], n["text"].replace("\n", "<br>"), st, n["x"], n["y"], n["w"], n["h"])
            elif k == "ellipse":
                vcell(n["id"], n["text"].replace("\n", "<br>"), f'ellipse;whiteSpace=wrap;html=1;fillColor={n["fill"]};strokeColor={BLUE};fontColor={NAVY};fontSize=12;', n["x"], n["y"], n["w"], n["h"])
            elif k == "actor":
                vcell(n["id"], n["text"].replace("\n", "<br>"), f"shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;strokeColor={NAVY};fontColor={NAVY};fontStyle=1;", n["x"] + 5, n["y"], 30, 70)
            elif k == "class":
                head = (f'<i style="font-size:10px;color:#64748b">{escape(n["stereo"])}</i><br>' if n["stereo"] else "") + f'<b>{escape(n["name"])}</b>'
                body = f'<p style="margin:0;text-align:center;background:{n["header"]}">{head}</p>' + ('<hr size="1"><div style="text-align:left;padding-left:6px;font-family:Courier New;font-size:11px">' + "<br>".join(escape(a) for a in n["attrs"]) + "</div>" if n["attrs"] else "") + ('<hr size="1"><div style="text-align:left;padding-left:6px;font-family:Courier New;font-size:11px">' + "<br>".join(escape(m) for m in n["methods"]) + "</div>" if n["methods"] else "")
                vcell(n["id"], body, f'verticalAlign=top;align=left;overflow=fill;html=1;whiteSpace=wrap;fillColor=#ffffff;strokeColor={NAVY};', n["x"], n["y"], n["w"], n["h"])
            elif k == "lifeline":
                vcell(n["id"], n["text"].replace("\n", "<br>"), f'shape=umlLifeline;perimeter=lifelinePerimeter;whiteSpace=wrap;html=1;container=0;dropTarget=0;collapsible=0;recursiveResize=0;outlineConnect=0;portConstraint=eastwest;newEdgeStyle={{"curved":0,"rounded":0}};fillColor={n["fill"]};strokeColor={NAVY};fontStyle=1;', n["x"], n["y"], n["w"], n["bottom"] - n["y"])
                cells[-1] = cells[-1].replace(f'height="{n["bottom"] - n["y"]:.0f}"', f'height="{n["bottom"] - n["y"]:.0f}"')
        for x in self.extra:
            if x["kind"] == "frame":
                vcell(x["id"], x["label"], "shape=umlFrame;whiteSpace=wrap;html=1;width=120;height=26;fontStyle=1;strokeColor=#475569;fillColor=none;", x["x"], x["y"], x["w"], x["h"])
                if x["divider"]:
                    cells.append(f'<mxCell id="{x["id"]}d" value="{escape(x["divider_text"])}" style="endArrow=none;dashed=1;html=1;strokeColor=#475569;align=left;verticalAlign=bottom;fontColor=#475569;" edge="1" parent="1"><mxGeometry relative="1" as="geometry"><mxPoint x="{x["x"]:.0f}" y="{x["divider"]:.0f}" as="sourcePoint"/><mxPoint x="{x["x"] + x["w"]:.0f}" y="{x["divider"]:.0f}" as="targetPoint"/></mxGeometry></mxCell>')
            elif x["kind"] == "note":
                vcell(x["id"], x["text"].replace("\n", "<br>"), "shape=note;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacingLeft=6;fillColor=#fffbeb;strokeColor=#d97706;fontColor=#78350f;size=14;", x["x"], x["y"], x["w"], x["h"])
            elif x["kind"] == "label":
                vcell(x["id"], x["text"], f'text;html=1;align=left;verticalAlign=middle;fontStyle={1 if x["bold"] else 0};fontColor={x["color"]};', x["x"], x["y"] - 10, 400, 20)
        for e in self.edges:
            if e["kind"] == "msg":
                st = "html=1;verticalAlign=bottom;endArrow=block;endFill=1;" + ("dashed=1;endFill=0;endArrow=open;" if e["dashed"] else "")
                if e["selfcall"]:
                    cells.append(f'<mxCell id="{e["id"]}" value="{escape(e["label"])}" style="{st}align=left;" edge="1" parent="1"><mxGeometry relative="1" as="geometry"><mxPoint x="{e["x1"]:.0f}" y="{e["y"]:.0f}" as="sourcePoint"/><mxPoint x="{e["x1"] + 4:.0f}" y="{e["y"] + 20:.0f}" as="targetPoint"/><Array as="points"><mxPoint x="{e["x1"] + 42:.0f}" y="{e["y"]:.0f}"/><mxPoint x="{e["x1"] + 42:.0f}" y="{e["y"] + 20:.0f}"/></Array></mxGeometry></mxCell>')
                else:
                    cells.append(f'<mxCell id="{e["id"]}" value="{escape(e["label"])}" style="{st}" edge="1" parent="1"><mxGeometry relative="1" as="geometry"><mxPoint x="{e["x1"]:.0f}" y="{e["y"]:.0f}" as="sourcePoint"/><mxPoint x="{e["x2"]:.0f}" y="{e["y"]:.0f}" as="targetPoint"/></mxGeometry></mxCell>')
                continue
            k = e["kind"]
            st = {"assoc": "endArrow=none;", "arrow": "endArrow=block;endFill=1;", "seq": "endArrow=block;endFill=1;",
                  "dep": "dashed=1;endArrow=open;endFill=0;strokeColor=#64748b;", "include": "dashed=1;endArrow=open;endFill=0;fontStyle=2;",
                  "extend": "dashed=1;endArrow=open;endFill=0;fontStyle=2;", "inherit": "endArrow=block;endFill=0;endSize=14;",
                  "compose": "startArrow=diamondThin;startFill=1;startSize=14;endArrow=none;"}[k]
            pts = "".join(f'<mxPoint x="{p[0]:.0f}" y="{p[1]:.0f}"/>' for p in e["pts"])
            arr = f'<Array as="points">{pts}</Array>' if pts else ""
            cells.append(f'<mxCell id="{e["id"]}" value="{escape(e["label"])}" style="html=1;{st}strokeColor={GREY if k == "dep" else NAVY};" edge="1" parent="1" source="{self.nodes[e["a"]]["id"]}" target="{self.nodes[e["b"]]["id"]}"><mxGeometry relative="1" as="geometry">{arr}</mxGeometry></mxCell>')
            for tag, txt, pos in (("s", e["a_lbl"], -0.85), ("t", e["b_lbl"], 0.85)):
                if txt:
                    cells.append(f'<mxCell id="{e["id"]}{tag}" value="{escape(txt)}" style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];fontColor=#b45309;fontStyle=1;" vertex="1" connectable="0" parent="{e["id"]}"><mxGeometry x="{pos}" relative="1" as="geometry"><mxPoint y="-10" as="offset"/></mxGeometry></mxCell>')
        xml = (f'<mxfile host="app.diagrams.net"><diagram name="{escape(self.title)}" id="d1"><mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{self.w}" pageHeight="{self.h}" math="0" shadow="0"><root>'
               + "".join(cells) + "</root></mxGraphModel></diagram></mxfile>")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(xml)
