import ctypes
import json
import sys

import psutil
import keyboard

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_uint),
        ('dwTime', ctypes.c_ulong),
    ]

def get_idle_duration():
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000

class WindowOverlay(QWidget):
    signal_toggle_drag = pyqtSignal()
    signal_toggle_hide = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
            # Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.setGeometry(
            config['window_spec']['x'],
            config['window_spec']['y'],
            config['window_spec']['w'],
            config['window_spec']['h'],
        )

        self.layout = QVBoxLayout()

        self.l_cpu = QLabel(self)
        self.l_cpu.setAlignment(Qt.AlignLeft)
        self.l_cpu.setStyleSheet(config['qt']['qlabel_stylesheet'])
        self.l_cpu.setMaximumWidth(self.width())
        self.l_cpu.setWordWrap(True)
        self.layout.addWidget(self.l_cpu)

        self.l_mem = QLabel(self)
        self.l_mem.setAlignment(Qt.AlignLeft)
        self.l_mem.setStyleSheet(config['qt']['qlabel_stylesheet'])
        self.l_mem.setMaximumWidth(self.width())
        self.l_mem.setWordWrap(True)
        self.layout.addWidget(self.l_mem)

        self.l_disk = QLabel(self)
        self.l_disk.setAlignment(Qt.AlignLeft)
        self.l_disk.setStyleSheet(config['qt']['qlabel_stylesheet'])
        self.l_disk.setMaximumWidth(self.width())
        self.l_disk.setWordWrap(True)
        self.layout.addWidget(self.l_disk)

        self.l_status = QLabel('Initializing...', self)
        self.l_status.setAlignment(Qt.AlignLeft)
        self.l_status.setStyleSheet(config['qt']['qlabel_stylesheet'])
        self.l_status.setMaximumWidth(self.width())
        self.l_status.setWordWrap(True)
        self.layout.addWidget(self.l_status)

        self.setLayout(self.layout)

        self.timer_update_stats = QTimer(self)
        self.timer_update_stats.timeout.connect(self.update_stats)
        self.timer_update_stats.start(config['update_interval_s'] * 1000)

        self.timer_check_idle = QTimer(self)
        self.timer_check_idle.timeout.connect(self.check_idle)
        self.timer_check_idle.start(config['update_interval_s'] * 1000)

        self.signal_toggle_drag.connect(self.toggle_drag)
        keyboard.add_hotkey(config['shortcut']['toggle_drag'], self.signal_toggle_drag.emit)

        self.signal_toggle_hide.connect(self.toggle_hide)
        keyboard.add_hotkey(config['shortcut']['toggle_hide'], self.signal_toggle_hide.emit)

        self.prev_disk_io = None

        self.draggable = False
        self.drag_pos = None

        self.is_idle = False

        self.l_status.setText('')
    
    def update_stats(self):
        cpu_percent = psutil.cpu_percent()
        cpus_percent = psutil.cpu_percent(percpu=True)

        mem_usage = psutil.virtual_memory()
        disk_io = psutil.disk_io_counters()

        self.l_cpu.setText(
            f'CPU:  {cpu_percent}%\n'
            f'CPUs: {cpus_percent}%'
        )
        self.l_cpu.adjustSize()

        mem_used = mem_usage.used/1024/1024
        mem_total = mem_usage.total/1024/1024
        self.l_mem.setText(f'Memory: {mem_used:.2f}/{mem_total:.2f} MB')
        self.l_mem.adjustSize()

        if self.prev_disk_io is not None:
            disk_read = (disk_io.read_bytes - self.prev_disk_io.read_bytes)/1024/1024
            disk_write = (disk_io.write_bytes - self.prev_disk_io.write_bytes)/1024/1024
            disk_read /= config['update_interval_s']
            disk_write /= config['update_interval_s']
            self.l_disk.setText(f'Disk: {disk_read:.2f}/{disk_write:.2f} MB/s')
        else:
            self.l_disk.setText(f'Disk: -/- MB/s')
        self.prev_disk_io = disk_io
        self.l_disk.adjustSize()
    
    def check_idle(self):
        idle_duration = get_idle_duration()
        if idle_duration > config['idle_after_s']:
            self.is_idle = True
            self.timer_update_stats.stop()
            self.l_status.setText('IDLED: Suspended')
        else:
            if self.is_idle:
                self.is_idle = False
                self.timer_update_stats.start()
                self.l_status.setText('')
    
    def toggle_drag(self):
        self.draggable = not self.draggable
        if self.draggable:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.l_status.setText('UNLOCKED: Drag to move')
        else:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.l_status.setText('')
    
    def toggle_hide(self):
        if self.isVisible():
            self.timer_update_stats.stop()
            self.timer_check_idle.stop()
            self.hide()
        else:
            self.timer_update_stats.start()
            self.timer_check_idle.start()
            self.show()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.draggable and event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.draggable and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.draggable and event.button() == Qt.LeftButton:
            self.save_window_pos()
            event.accept()

    def save_window_pos(self):
        config['window_spec']['x'] = self.x()
        config['window_spec']['y'] = self.y()
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)

def main():
    global config
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        with open('config_default.json', 'r') as f:
            config = json.load(f)

    app = QApplication(sys.argv)
    widget = WindowOverlay()
    widget.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
