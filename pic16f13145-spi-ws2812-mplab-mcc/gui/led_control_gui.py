#!/usr/bin/env python3
"""
Tkinter control panel for the PIC16 WS2812 UART firmware.

Commands sent match led_protocol.c (line-terminated with CR+LF):
  L<n> R G B [W]  — single LED
  A R G B [W]     — all LEDs
  C               — clear
  U               — refresh strip
  M <3|4>         — set mode: 3=RGB, 4=RGBW
"""

from __future__ import annotations

import math
import queue
import threading
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

try:
    import serial
    import serial.tools.list_ports
except ImportError as exc:
    raise SystemExit(
        "Missing pyserial. From the gui folder, run scripts\\build.bat or scripts\\build.ps1."
    ) from exc

DEFAULT_NUM_LEDS = 8
DEFAULT_BAUD = 115200
BAUD_CHOICES = (9600, 19200, 38400, 57600, 115200)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


class RgbEditorDialog(tk.Toplevel):
    """Modal popup to edit R,G,B[,W] (0-255). Returns tuple on OK or None on cancel."""

    def __init__(
        self,
        master: tk.Widget,
        title: str,
        initial: tuple[int, ...] = (0, 0, 0),
        rgbw_mode: bool = False,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self._result: tuple[int, ...] | None = None
        self._rgbw_mode = rgbw_mode

        r0, g0, b0 = initial[0], initial[1], initial[2]
        w0 = initial[3] if len(initial) > 3 else 0
        self._var_r = tk.IntVar(value=r0)
        self._var_g = tk.IntVar(value=g0)
        self._var_b = tk.IntVar(value=b0)
        self._var_w = tk.IntVar(value=w0)

        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")

        preview = tk.Canvas(body, width=180, height=40, highlightthickness=1)
        preview.grid(row=0, column=0, columnspan=3, pady=(0, 10))
        self._preview = preview

        def mk_row(row: int, label: str, var: tk.IntVar) -> None:
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w")
            spin = ttk.Spinbox(
                body,
                from_=0,
                to=255,
                width=6,
                textvariable=var,
                command=self._refresh_preview,
            )
            spin.grid(row=row, column=1, sticky="w", padx=(8, 0))
            scale = ttk.Scale(
                body,
                from_=0,
                to=255,
                orient=tk.HORIZONTAL,
                length=200,
                command=lambda _: self._refresh_preview(),
                variable=var,
            )
            scale.grid(row=row, column=2, padx=(12, 0))

        mk_row(1, "Red", self._var_r)
        mk_row(2, "Green", self._var_g)
        mk_row(3, "Blue", self._var_b)

        next_row = 4
        if self._rgbw_mode:
            mk_row(4, "White", self._var_w)
            next_row = 5

        ttk.Button(body, text="Color picker…", command=self._pick_color).grid(
            row=next_row, column=0, columnspan=3, pady=(10, 0), sticky="w"
        )

        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.grid(row=1, column=0, sticky="ew")
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        ttk.Button(buttons, text="OK", command=self._ok).pack(side=tk.RIGHT)

        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._refresh_preview()
        self.wait_window(self)

    def _color(self) -> tuple[int, ...]:
        r = max(0, min(255, self._var_r.get()))
        g = max(0, min(255, self._var_g.get()))
        b = max(0, min(255, self._var_b.get()))
        if self._rgbw_mode:
            w = max(0, min(255, self._var_w.get()))
            return (r, g, b, w)
        return (r, g, b)

    def _refresh_preview(self, *_args: object) -> None:
        r = max(0, min(255, self._var_r.get()))
        g = max(0, min(255, self._var_g.get()))
        b = max(0, min(255, self._var_b.get()))
        if self._rgbw_mode:
            w = max(0, min(255, self._var_w.get()))
            r = min(255, r + w)
            g = min(255, g + w)
            b = min(255, b + w)
        self._preview.configure(bg=rgb_to_hex(r, g, b))

    def _pick_color(self) -> None:
        r = max(0, min(255, self._var_r.get()))
        g = max(0, min(255, self._var_g.get()))
        b = max(0, min(255, self._var_b.get()))
        init = rgb_to_hex(r, g, b)
        triple, _hex = colorchooser.askcolor(color=init, parent=self)
        if triple is None:
            return
        r, g, b = (int(round(x)) for x in triple)
        self._var_r.set(max(0, min(255, r)))
        self._var_g.set(max(0, min(255, g)))
        self._var_b.set(max(0, min(255, b)))
        self._refresh_preview()

    def _ok(self) -> None:
        self._result = self._color()
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self._result = None
        self.grab_release()
        self.destroy()


class LedControlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("WS2812 UART — LED control")
        self.minsize(560, 480)

        self._ser: serial.Serial | None = None
        self._reader_stop = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._rx_queue: queue.Queue[str] = queue.Queue()

        self._num_leds = DEFAULT_NUM_LEDS
        self._rgbw_mode = False
        self._led_colors: list[tuple[int, ...]] = [(32, 32, 32)] * self._num_leds
        self._intensity = tk.IntVar(value=100)
        self._led_hit: list[tuple[float, float, float]] = []

        self._build_ui()
        self._poll_rx_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Port").pack(side=tk.LEFT)
        self._port_combo = ttk.Combobox(top, width=28, state="readonly")
        self._port_combo.pack(side=tk.LEFT, padx=(6, 12))

        ttk.Label(top, text="Baud").pack(side=tk.LEFT)
        self._baud_combo = ttk.Combobox(
            top,
            width=8,
            values=tuple(str(b) for b in BAUD_CHOICES),
            state="readonly",
        )
        self._baud_combo.set(str(DEFAULT_BAUD))
        self._baud_combo.pack(side=tk.LEFT, padx=(6, 12))

        self._btn_refresh_ports = ttk.Button(
            top, text="Refresh ports", command=self._refresh_ports
        )
        self._btn_refresh_ports.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_connect = ttk.Button(
            top, text="Connect", command=self._toggle_connect
        )
        self._btn_connect.pack(side=tk.LEFT)

        self._refresh_ports()

        config_frame = ttk.LabelFrame(self, text="Configuration", padding=8)
        config_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        ttk.Label(config_frame, text="Number of LEDs:").pack(side=tk.LEFT)
        self._num_leds_var = tk.IntVar(value=DEFAULT_NUM_LEDS)
        self._num_leds_spin = ttk.Spinbox(
            config_frame, from_=1, to=64, width=4, textvariable=self._num_leds_var
        )
        self._num_leds_spin.pack(side=tk.LEFT, padx=(4, 16))

        self._mode_var = tk.StringVar(value="RGB")
        ttk.Radiobutton(
            config_frame, text="RGB (3-color)", variable=self._mode_var, value="RGB"
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            config_frame, text="RGBW (4-color)", variable=self._mode_var, value="RGBW"
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(config_frame, text="Apply", command=self._apply_config).pack(
            side=tk.LEFT, padx=(16, 0)
        )

        strip = ttk.LabelFrame(
            self,
            text="LEDs in a circle — 0 at bottom, increasing counter-clockwise — click to set color",
            padding=8,
        )
        strip.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))

        self._canvas = tk.Canvas(
            strip,
            height=300,
            bg="#202020",
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind("<Button-1>", self._on_canvas_click)

        actions = ttk.Frame(self, padding=(8, 0))
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Set all LEDs…", command=self._edit_all).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(actions, text="Clear strip", command=self._send_clear).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(actions, text="Send U (refresh)", command=self._send_refresh).pack(
            side=tk.LEFT
        )

        dim_frame = ttk.Frame(self, padding=(8, 6))
        dim_frame.pack(fill=tk.X)
        ttk.Label(dim_frame, text="Intensity").pack(side=tk.LEFT)
        self._intensity_label = ttk.Label(dim_frame, text="100%", width=5)
        self._intensity_label.pack(side=tk.RIGHT)
        ttk.Scale(
            dim_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self._intensity,
            command=self._on_intensity_change,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))

        log_fr = ttk.LabelFrame(self, text="Serial (RX)", padding=8)
        log_fr.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self._rx_text = tk.Text(log_fr, height=10, state=tk.DISABLED, wrap=tk.WORD)
        self._rx_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(log_fr, command=self._rx_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._rx_text.configure(yscrollcommand=sb.set)

        hint = ttk.Label(
            self,
            text="Tip: disable local echo in other terminals to avoid double characters.",
            foreground="#555",
        )
        hint.pack(pady=(0, 8))

    def _apply_config(self) -> None:
        new_count = max(1, min(64, self._num_leds_var.get()))
        new_rgbw = self._mode_var.get() == "RGBW"

        old = self._led_colors
        converted: list[tuple[int, ...]] = []
        for i in range(new_count):
            if i < len(old):
                c = old[i]
                if new_rgbw:
                    converted.append((c[0], c[1], c[2], c[3] if len(c) > 3 else 0))
                else:
                    converted.append((c[0], c[1], c[2]))
            else:
                if new_rgbw:
                    converted.append((32, 32, 32, 0))
                else:
                    converted.append((32, 32, 32))

        self._led_colors = converted
        self._num_leds = new_count
        self._rgbw_mode = new_rgbw

        mode_val = 4 if new_rgbw else 3
        self._send_line(f"M {mode_val}")

        self._draw_led_strip()

    def _refresh_ports(self) -> None:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self._port_combo.configure(values=ports)
        if ports and self._port_combo.get() not in ports:
            self._port_combo.current(0)

    def _toggle_connect(self) -> None:
        if self._ser is not None and self._ser.is_open:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        port = self._port_combo.get().strip()
        if not port:
            messagebox.showwarning("Serial", "Select a COM port.")
            return
        try:
            baud = int(self._baud_combo.get())
        except ValueError:
            messagebox.showwarning("Serial", "Invalid baud rate.")
            return

        try:
            self._ser = serial.Serial(port=port, baudrate=baud, timeout=0.2)
        except serial.SerialException as exc:
            messagebox.showerror("Serial", str(exc))
            self._ser = None
            return

        self._reader_stop.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        self._btn_connect.configure(text="Disconnect")
        self._log_rx(f"[Connected {port} @ {baud}]\n")

    def _disconnect(self) -> None:
        self._reader_stop.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2.0)
            self._reader_thread = None

        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

        self._btn_connect.configure(text="Connect")
        self._log_rx("[Disconnected]\n")

    def _reader_loop(self) -> None:
        assert self._ser is not None
        while not self._reader_stop.is_set():
            try:
                waiting = self._ser.in_waiting
                if waiting:
                    chunk = self._ser.read(waiting)
                    self._rx_queue.put(chunk.decode("utf-8", errors="replace"))
                else:
                    time.sleep(0.03)
            except Exception as exc:
                self._rx_queue.put(f"\n[read error: {exc}]\n")
                break

    def _poll_rx_queue(self) -> None:
        try:
            while True:
                text = self._rx_queue.get_nowait()
                self._log_rx(text)
        except queue.Empty:
            pass
        self.after(80, self._poll_rx_queue)

    def _log_rx(self, text: str) -> None:
        self._rx_text.configure(state=tk.NORMAL)
        self._rx_text.insert(tk.END, text)
        self._rx_text.see(tk.END)
        self._rx_text.configure(state=tk.DISABLED)

    def _send_line(self, line: str) -> bool:
        if self._ser is None or not self._ser.is_open:
            messagebox.showwarning("Serial", "Not connected.")
            return False
        payload = line.strip() + "\r\n"
        try:
            self._ser.write(payload.encode("ascii", errors="strict"))
            self._log_rx(f">> {line.strip()}\n")
            return True
        except Exception as exc:
            messagebox.showerror("Serial", f"Write failed: {exc}")
            return False

    def _on_canvas_resize(self, _event: tk.Event) -> None:
        self._draw_led_strip()

    def _draw_led_strip(self) -> None:
        self._canvas.delete("all")
        w = max(self._canvas.winfo_width(), 10)
        h = max(self._canvas.winfo_height(), 10)

        pad = 20
        cx = w * 0.5
        cy = h * 0.5
        short = max(min(w, h) - 2 * pad, 40)

        n = float(self._num_leds)
        led_radius = max(10.0, min(26.0, short * 0.09))
        label_margin = led_radius + 14.0

        ring_min = (
            led_radius / max(math.sin(math.pi / n), 1e-6)
            if self._num_leds >= 2
            else led_radius
        )
        ring_ceiling = max(short * 0.5 - label_margin, ring_min)
        ring_r = max(short * 0.38, ring_min * 1.08)
        ring_r = min(ring_r, ring_ceiling)
        ring_r = max(ring_r, ring_min)

        self._canvas.create_oval(
            cx - ring_r,
            cy - ring_r,
            cx + ring_r,
            cy + ring_r,
            outline="#444",
            dash=(5, 6),
            width=1,
        )

        theta0 = 1.5 * math.pi
        step = (2.0 * math.pi) / n

        self._led_hit.clear()
        for i in range(self._num_leds):
            theta = theta0 - step * i
            lx = cx + ring_r * math.cos(theta)
            ly = cy - ring_r * math.sin(theta)
            self._led_hit.append((lx, ly, led_radius))

            color = self._led_colors[i]
            r, g, b = color[0], color[1], color[2]
            if len(color) > 3:
                ww = color[3]
                r = min(255, r + ww)
                g = min(255, g + ww)
                b = min(255, b + ww)
            dr, dg, db = self._dimmed_color(r, g, b)
            fill = rgb_to_hex(dr, dg, db)
            self._canvas.create_oval(
                lx - led_radius,
                ly - led_radius,
                lx + led_radius,
                ly + led_radius,
                fill=fill,
                outline="#888",
                width=2,
                tags=("led", str(i)),
            )

            ux = math.cos(theta)
            uy = -math.sin(theta)
            tx = lx + ux * label_margin
            ty = ly + uy * label_margin
            self._canvas.create_text(
                tx,
                ty,
                text=str(i),
                fill="#ccc",
                font=("Segoe UI", 10),
            )

    def _hit_led(self, x: float, y: float) -> int | None:
        for idx, (cx, cy, r) in enumerate(self._led_hit):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy <= r * r:
                return idx
        return None

    def _on_canvas_click(self, event: tk.Event) -> None:
        idx = self._hit_led(event.x, event.y)
        if idx is None:
            return
        self._edit_led(idx)

    def _edit_led(self, idx: int) -> None:
        dlg = RgbEditorDialog(
            self,
            title=f"LED {idx} — {'RGBW' if self._rgbw_mode else 'RGB'}",
            initial=self._led_colors[idx],
            rgbw_mode=self._rgbw_mode,
        )
        if dlg._result is None:
            return
        self._led_colors[idx] = dlg._result
        self._draw_led_strip()
        dimmed = self._dimmed_color(*dlg._result)
        if self._rgbw_mode:
            self._send_line(f"L{idx} {dimmed[0]} {dimmed[1]} {dimmed[2]} {dimmed[3]}")
        else:
            self._send_line(f"L{idx} {dimmed[0]} {dimmed[1]} {dimmed[2]}")

    def _edit_all(self) -> None:
        dlg = RgbEditorDialog(
            self,
            title=f"All LEDs — {'RGBW' if self._rgbw_mode else 'RGB'}",
            initial=self._led_colors[0],
            rgbw_mode=self._rgbw_mode,
        )
        if dlg._result is None:
            return
        self._led_colors = [dlg._result] * self._num_leds
        self._draw_led_strip()
        dimmed = self._dimmed_color(*dlg._result)
        if self._rgbw_mode:
            self._send_line(f"A {dimmed[0]} {dimmed[1]} {dimmed[2]} {dimmed[3]}")
        else:
            self._send_line(f"A {dimmed[0]} {dimmed[1]} {dimmed[2]}")

    def _send_clear(self) -> None:
        if not self._send_line("C"):
            return
        if self._rgbw_mode:
            self._led_colors = [(0, 0, 0, 0)] * self._num_leds
        else:
            self._led_colors = [(0, 0, 0)] * self._num_leds
        self._draw_led_strip()

    def _send_refresh(self) -> None:
        self._send_line("U")

    def _dimmed_color(self, *components: int) -> tuple[int, ...]:
        scale = self._intensity.get() / 100.0
        return tuple(int(c * scale) for c in components)

    def _on_intensity_change(self, _val: str) -> None:
        pct = self._intensity.get()
        self._intensity_label.configure(text=f"{pct}%")
        self._draw_led_strip()
        if self._ser is None or not self._ser.is_open:
            return
        for i, color in enumerate(self._led_colors):
            dimmed = self._dimmed_color(*color)
            if self._rgbw_mode:
                self._send_line(
                    f"L{i} {dimmed[0]} {dimmed[1]} {dimmed[2]} {dimmed[3]}"
                )
            else:
                self._send_line(f"L{i} {dimmed[0]} {dimmed[1]} {dimmed[2]}")

    def _on_close(self) -> None:
        self._disconnect()
        self.destroy()


def main() -> None:
    app = LedControlApp()
    app.mainloop()


if __name__ == "__main__":
    main()
