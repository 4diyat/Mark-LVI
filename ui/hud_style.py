"""Styles for the two-zone desktop home, using a restrained navy/blue palette."""
STYLE = '''
QWidget#mainSurface { background:#030811; color:#edf5ff; }
QLabel { color:#edf5ff; background:transparent; }
QLabel#brand { color:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #96d9ff,stop:1 #1687ff); font-size:23px; font-weight:700; letter-spacing:3px; }
QLabel#eyebrow { color:#bdc9d8; font-size:11px; letter-spacing:1px; }
QLabel#muted, QLabel#quickDesc { color:#c0ccdb; font-size:14px; }
QLabel#pageTitle { font-size:24px; font-weight:700; }
QLabel#sectionTitle { font-size:16px; font-weight:600; }
QLabel#cardTitle { color:#f7faff; font-size:16px; font-weight:600; }
QLabel#metricValue { color:#cce6ff; font-size:15px; font-weight:600; }
QLabel#accentIcon { color:#65bcff; font-size:21px; }
QLabel#toastTitle { font-size:16px; font-weight:600; }
QLabel#state, QLabel#connection, QLabel#orbState { color:#ced9e6; font-size:14px; }
QLabel#feedback { color:#ffd69b; background:#35291d; border:1px solid #7c6140; border-radius:9px; padding:8px; font-size:14px; }
QLabel#avatar { background:qradialgradient(cx:0.35,cy:0.3,radius:0.8,fx:0.3,fy:0.2,stop:0 #1a67ba,stop:1 #061323); border:1px solid #458fd4; border-radius:29px; }
QScrollArea { background:transparent; border:0; }
QScrollArea > QWidget > QWidget { background:transparent; }
QFrame#toast, QFrame#homePanel { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #111b29,stop:0.5 #0a121d,stop:1 #070c14); border:1px solid #39495c; border-radius:18px; }
QFrame#segmented { background:#080e17; border:1px solid #394a60; border-radius:12px; }
QPushButton#nav { background:transparent; color:#c2cfdf; border:0; border-radius:10px; padding:10px 8px; font-size:14px; }
QPushButton#nav:checked { color:#e3f4ff; background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #205a9b,stop:1 #0a203e); border:1px solid #58b9ff; border-bottom:3px solid #57baff; }
QPushButton#nav:disabled { color:#7e8d9e; }
QPushButton#quickCard, QPushButton#moduleCard { text-align:left; background:qlineargradient(x1:0,y1:0,x2:0.4,y2:1,stop:0 #162333,stop:1 #0c1520); border:1px solid #3b4d61; border-radius:12px; }
QPushButton#quickCard:hover, QPushButton#moduleCard:hover { border:1px solid #69bdff; background:#192e44; }
QPushButton#quickCard:disabled QLabel#cardTitle { color:#a6b5c8; }
QPushButton#quickCard:disabled QLabel#quickDesc { color:#a4b3c4; }
QPushButton#quickCard:disabled, QPushButton#moduleCard:disabled { background:#101923; border-color:#2c3947; }
QPushButton#secondary { background:#152234; color:#d1deec; border:1px solid #40536a; border-radius:10px; padding:7px 12px; }
QPushButton#secondary:hover { border-color:#68baff; }
QPushButton#secondary:disabled { color:#8797aa; border-color:#344255; }
QPushButton#closeToast { background:transparent; border:0; }
QPushButton#micSmall { background:transparent; border:0; }
QPushButton#sparkle { background:#192638; border:1px solid #3b5067; border-radius:10px; }
QPushButton#sparkle:disabled { background:#121c28; }
QPushButton#send { color:white; background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #339cff,stop:1 #0866e7); border:1px solid #8bd2ff; border-radius:12px; padding:8px 20px; font-size:16px; font-weight:700; }
QPushButton#send:disabled { background:#293d55; color:#9eafc0; border-color:#3f5366; }
QFrame#composer, QFrame#resultCard, QFrame#metric, QFrame#retryPanel { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #131f2d,stop:1 #0c1520); border:1px solid #3c5065; border-radius:12px; }
QFrame#micDivider { background:#35485b; }
QLineEdit { color:#f6faff; background:transparent; border:0; font-size:15px; padding:8px; }
QLineEdit:disabled { color:#8796aa; }
QTextBrowser, QFrame#emptyPanel { color:#e9f2ff; background:#09121d; border:1px solid #293b4f; border-radius:12px; padding:12px; font-size:15px; }
QLabel#emptyTitle { color:#e7f1fd; font-size:17px; font-weight:600; }
QLabel#emptyDescription { color:#c4d0de; font-size:14px; }
QProgressBar { background:#263c50; border:0; border-radius:3px; }
QProgressBar::chunk { background:#50afff; border-radius:3px; }
QCheckBox { color:#bdcbdb; font-size:13px; spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #58718b; border-radius:4px; background:#101b2b; }
QCheckBox::indicator:checked { background:#328ee9; border-color:#7ac8ff; }
QScrollBar:vertical { background:#101b28; width:8px; margin:0; }
QScrollBar::handle:vertical { background:#4f6b87; border-radius:4px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { background:#101b28; height:8px; margin:0; }
QScrollBar::handle:horizontal { background:#4f6b87; border-radius:4px; min-width:30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
QMenu { background:#14202f; border:1px solid #40536a; color:#e6f1ff; padding:5px; }
QMenu::item { padding:8px 18px; border-radius:6px; }
QMenu::item:selected { background:#214d7c; }
'''
