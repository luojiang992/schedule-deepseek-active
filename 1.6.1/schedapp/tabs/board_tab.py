# -*- coding: utf-8 -*-
"""「画板」标签页"""
import os

from ..paths import BOARD_COLORS


class BoardTabMixin:
    def _build_board_tab(self, nb, tk, ttk):
        self.tab_board = ttk.Frame(nb)
        nb.add(self.tab_board, text="  画板  ")
        bbar = ttk.Frame(self.tab_board)
        bbar.pack(fill="x", padx=4, pady=4)
        ttk.Label(bbar, text="颜色:").pack(side="left")
        for c in BOARD_COLORS:
            tk.Button(bbar, text="", width=2, bg=c,
                      command=lambda cc=c: self.board_set_color(cc)).pack(
                side="left", padx=1)
        self.board_eraser_btn = ttk.Button(bbar, text="◻ 橡皮",
                                           command=self.board_toggle_eraser)
        self.board_eraser_btn.pack(side="left", padx=4)
        ttk.Label(bbar, text="粗细:").pack(side="left")
        self.board_width_var = tk.StringVar(value="中")
        for wlabel, wv in (("细", 3), ("中", 6), ("粗", 12)):
            ttk.Radiobutton(bbar, text=wlabel, value=wlabel,
                            variable=self.board_width_var,
                            command=lambda: setattr(
                                self, "board_width",
                                {"细": 3, "中": 6, "粗": 12}[self.board_width_var.get()])
                            ).pack(side="left", padx=2)
        ttk.Button(bbar, text="🧹 清空全部", command=self.board_clear).pack(side="left", padx=6)
        ttk.Button(bbar, text="💾 保存 PNG", command=self.board_save).pack(side="left", padx=6)
        ttk.Button(bbar, text="🖼 打开图片", command=self.board_open).pack(side="left", padx=6)
        ttk.Button(bbar, text="⬜ 白板", command=self.board_white).pack(side="left", padx=6)

        bw = ttk.Frame(self.tab_board)
        bw.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.board_canvas = tk.Canvas(bw, bg="#ffffff", width=960, height=620,
                                      cursor="crosshair", highlightthickness=0)
        hsb = ttk.Scrollbar(bw, orient="horizontal", command=self.board_canvas.xview)
        vsb = ttk.Scrollbar(bw, orient="vertical", command=self.board_canvas.yview)
        self.board_canvas.configure(xscrollcommand=hsb.set, yscrollcommand=vsb.set)
        self.board_canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        bw.rowconfigure(0, weight=1)
        bw.columnconfigure(0, weight=1)
        self.board_canvas.bind("<ButtonPress-1>", self.board_press)
        self.board_canvas.bind("<B1-Motion>", self.board_motion)
        self.board_canvas.bind("<ButtonRelease-1>", self.board_release)
        self.board_white()

    def board_set_color(self, color):
        self.board_color = color
        self.board_eraser = False
        self.board_eraser_btn.configure(text="◻ 橡皮")

    def board_toggle_eraser(self):
        self.board_eraser = not self.board_eraser
        self.board_eraser_btn.configure(text="✏ 画笔" if self.board_eraser else "◻ 橡皮")

    def board_press(self, ev):
        self.board_drawing = {
            "pts": [(ev.x, ev.y)], "color": self.board_color,
            "w": self.board_width, "eraser": self.board_eraser}
        self.board_canvas.create_line(ev.x, ev.y, ev.x + 1, ev.y + 1,
                                      fill=("#ffffff" if self.board_eraser
                                            else self.board_color),
                                      width=self.board_width, capstyle="round")

    def board_motion(self, ev):
        if self.board_drawing is None:
            return
        pts = self.board_drawing["pts"]
        pts.append((ev.x, ev.y))
        self.board_canvas.create_line(pts[-2][0], pts[-2][1], ev.x, ev.y,
                                      fill=("#ffffff" if self.board_drawing["eraser"]
                                            else self.board_drawing["color"]),
                                      width=self.board_drawing["w"], capstyle="round")

    def board_release(self, ev):
        if self.board_drawing is None:
            return
        self.board_strokes.append(self.board_drawing)
        self.board_drawing = None
        self.board_render()

    def _board_compose(self):
        """渲染当前笔画到 RGBA 图(橡皮打洞露出底图)"""
        from PIL import Image, ImageDraw, ImageChops
        size = self.board_base.size
        display = self.board_base.copy()
        ov = Image.new("RGBA", size, (0, 0, 0, 0))
        for s in self.board_strokes:
            if s["eraser"]:
                mask = Image.new("L", size, 0)
                ImageDraw.Draw(mask).line(s["pts"], fill=255, width=s["w"])
                ov.putalpha(ImageChops.multiply(ov.getchannel("A"),
                                                ImageChops.invert(mask)))
            else:
                ImageDraw.Draw(ov).line(s["pts"], fill=s["color"] + (255,),
                                        width=s["w"])
        display.alpha_composite(ov)
        return display

    def board_render(self):
        from PIL import ImageTk
        if self.board_base is None:
            return
        self.board_photo = ImageTk.PhotoImage(self._board_compose().convert("RGB"))
        self.board_canvas.delete("all")
        self.board_canvas.create_image(0, 0, anchor="nw", image=self.board_photo)

    def board_white(self):
        from PIL import Image
        self.board_base = Image.new("RGBA", (960, 620), (255, 255, 255, 255))
        self.board_strokes = []
        self.board_render()

    def board_clear(self):
        if not self._ask("确认清空", "确定清空画板上的全部笔迹吗？"):
            return
        self.board_strokes = []
        self.board_render()

    def board_save(self):
        tk, ttk, messagebox, filedialog, _ = self._need_tk()
        path = filedialog.asksaveasfilename(
            title="保存画板为 PNG", defaultextension=".png",
            filetypes=[("PNG 图片", "*.png")], initialfile="画板.png")
        if not path:
            return
        try:
            self._board_compose().convert("RGB").save(path)
            self._toast("画板已保存: %s" % os.path.basename(path))
        except Exception as e:
            self._err("保存失败: %s" % e)

    def board_open(self):
        tk, ttk, messagebox, filedialog, _ = self._need_tk()
        path = filedialog.askopenfilename(
            title="打开图片作为画板",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.gif *.webp")])
        if not path:
            return
        try:
            from PIL import Image
            img = Image.open(path)
            img.load()
            img = img.convert("RGBA")
            tw, th = 960, 620
            scale = min(tw / img.width, th / img.height)
            nw, nh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
            img = img.resize((nw, nh), Image.LANCZOS)
            base = Image.new("RGBA", (tw, th), (255, 255, 255, 255))
            base.paste(img, ((tw - nw) // 2, (th - nh) // 2), img)
            self.board_base = base
            self.board_strokes = []
            self.board_render()
            self._toast("已载入图片作为画板")
        except Exception as e:
            self._err("无法打开图片: %s" % e)
