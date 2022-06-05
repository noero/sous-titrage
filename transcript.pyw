#!/usr/bin/env python3

import os
import sys
import vosk  # pip install vosk
import json
import queue
import tkinter as tk
import sounddevice as sd  # pip install sounddevice
from threading import Thread

_Q = queue.Queue()
_SYSTEM = os.name


def get_curr_screen_width():
    root = tk.Tk()
    root.update_idletasks()
    root.attributes('-fullscreen', True)
    root.state('iconic')
    width = root.winfo_width()
    root.destroy()
    return width


def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


def callback_sd(outdata, frames, time, status):
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    _Q.put(bytes(outdata))


class App(tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        self.y = None
        self.x = None
        self.started = False
        self.stopped = False
        self.muted = False

        # Window settings
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        if _SYSTEM == 'nt':
            self.attributes("-transparentcolor", "green")
            color = 'green'
        else:
            color = self['bg']
        self.resizable(width=False, height=False)
        self.geometry("%dx%d%+d%+d" % (self.winfo_screenwidth(), 150, 0, (self.winfo_screenheight()-200)))

        # Frame settings
        self.Frame = tk.Frame(self, padx=0, pady=0, bg=color)
        self.Frame.place(relwidth=1, relheight=1)
        self.btnFrame = tk.Frame(self.Frame, padx=10, pady=0, bg=color)
        self.btnFrame.pack(side='left')
        self.txtFrame = tk.Frame(self.Frame, padx=5, pady=0, bg=color)
        self.txtFrame.pack(side='left', fill='both')

        # Button settings
        iconClose = tk.PhotoImage(file='./images/close.png')
        iconMove = tk.PhotoImage(file='./images/move.png')
        iconClean = tk.PhotoImage(file='./images/clean.png')
        iconMute = tk.PhotoImage(file='./images/mute.png')
        iconUnmute = tk.PhotoImage(file='./images/unmute.png')

        def closeCmd():
            print('******* Stopping ********')
            self.text.delete('1.0', 'end')
            self.text.insert('1.0', "Arrêt...", 'all')
            self.stopped = True

        def cleanCmd():
            self.text.delete('1.0', 'end')
            self.text.insert('1.0', "...", 'all')
            self.text.insert('1.end', "\n")

        def muteCmd():
            self.text.delete('1.0', 'end')
            self.text.insert('1.0', "...", 'all')
            self.text.insert('1.end', "\n")
            self.muted = not self.muted
            if self.muted:
                self.muteBtn.config(image=iconUnmute)
                self.muteBtn.image = iconUnmute
            else:
                self.muteBtn.config(image=iconMute)
                self.muteBtn.image = iconMute
        
        self.closeBtn = tk.Button(self.btnFrame, image=iconClose, relief='flat', command=closeCmd)
        self.closeBtn.grid(row=0, column=0, padx=5, pady=1)
        self.closeBtn.image = iconClose
        self.moveBtn = tk.Button(self.btnFrame, image=iconMove, relief='flat')
        self.moveBtn.grid(row=1, column=0, padx=5, pady=1)
        self.moveBtn.image = iconMove
        self.moveBtn.bind("<ButtonPress-1>", self.start_move)
        self.moveBtn.bind("<ButtonRelease-1>", self.stop_move)
        self.moveBtn.bind("<B1-Motion>", self.do_move)
        self.cleanBtn = tk.Button(self.btnFrame, image=iconClean, relief='flat', command=cleanCmd)
        self.cleanBtn.grid(row=2, column=0, padx=5, pady=1)
        self.cleanBtn.image = iconClean
        self.muteBtn = tk.Button(self.btnFrame, image=iconMute, relief='flat', command=muteCmd)
        self.muteBtn.grid(row=3, column=0, padx=5, pady=1)
        self.muteBtn.image = iconMute

        # Scroll settings
        text_scroll = tk.Scrollbar(self.txtFrame)
        text_scroll.pack(side=tk.LEFT, fill=tk.Y)

        # Text settings
        self.text = tk.Text(self.txtFrame, font=("Courrier", 18), wrap="word", relief="flat",
                            yscrollcommand=text_scroll.set, bg=color)
        self.text.pack(side="left", fill='both')
        self.text.tag_configure("low", foreground='#717171', background='black')
        self.text.tag_configure("medium", foreground='#BCBCBC', background='black')
        self.text.tag_configure('all', foreground='white', background='black')
        self.text.insert('end', "Initialisation ...", 'all')
        text_scroll.config(command=self.text.yview)

        self._thread = None

        if not self.started:
            if self._thread is None:
                self._thread = Thread(target=self.start_STT)
                self._thread.start()

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def stop_move(self, event):
        self.x = None
        self.y = None

    def do_move(self, event):
        delta_x = event.x - self.x
        delta_y = event.y - self.y
        x = self.winfo_x() + delta_x
        y = self.winfo_y() + delta_y
        self.geometry(f"+{x}+{y}")

    def start_STT(self):
        self.started = True
        try:
            modelPath = "./model"
            if not os.path.exists(modelPath):
                print("Please download a model for your language from https://alphacephei.com/vosk/models")
                print("and unpack as 'model' in the current folder.")
            device_info = sd.query_devices(None, 'input')
            samplerate = int(device_info['default_samplerate'])

            model = vosk.Model(modelPath)

            index = 0
            dev_index = None
            for dev in sd.query_devices():
                if 'Mix' in dev['name'] and dev['hostapi'] == 0:
                    dev_index = index
                    break
                index += 1
            if _SYSTEM == 'nt':
                sd.default.device = dev_index, None

            with sd.RawInputStream(samplerate=samplerate, blocksize=8000, device=None, dtype='int16',
                                   channels=1, callback=callback_sd):

                rec = vosk.KaldiRecognizer(model, samplerate)
                rec.SetWords(True)
                complete = False
                words = []
                self.text.delete('1.0', 'end')
                self.text.insert('1.0', "...", 'all')
                self.text.insert('1.end', "\n")

                print('******* Listening ********')

                while True:
                    data = _Q.get()
                    if self.stopped:
                        break
                    if not self.muted:
                        if rec.AcceptWaveform(data):
                            res = json.loads(rec.Result())
                            if res["text"] != "":
                                words = res["result"]
                                self.text.delete('2.0', '2.end')
                                for word in words:
                                    if word["conf"] < 0.6:
                                        tag = "low"
                                    elif word["conf"] < 0.8:
                                        tag = "medium"
                                    else:
                                        tag = 'all'
                                    self.text.insert('2.end', word['word'] + " ", tag)
                                self.text.delete('2.end', 'end')
                                self.text.insert('end', "\n")
                                complete = True
                        else:
                            res = json.loads(rec.PartialResult())
                            if res["partial"] != "":
                                # text = self.text.get('2.0', '2.end')
                                if self.text.index('2.end') != '2.0':
                                    self.text.delete('2.0', '2.end')
                                if complete:
                                    self.text.delete('1.0', '1.end')
                                    for word in words:
                                        if word["conf"] < 0.6:
                                            tag = "low"
                                        elif word["conf"] < 0.8:
                                            tag = "medium"
                                        else:
                                            tag = 'all'
                                        self.text.insert('1.end', word['word'] + " ", tag)
                                self.text.insert('2.0', res["partial"] + ' ', 'all')
                                complete = False

            self.quit()

        except Exception as e:
            print(e)
            self.quit()


App().mainloop()
