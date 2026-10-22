from .config import resource


STYLE = """
QWidget { background: #11141c; color: #e4e7f1; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
QMainWindow, QDialog { background: #11141c; }
QPushButton, QToolButton { background: #232837; border: 1px solid #343b50; border-radius: 7px; padding: 8px 12px; }
QToolButton { padding: 8px 10px; }
QToolButton[split="true"] { padding-right: 28px; }
QPushButton:focus, QToolButton:focus { border-color: #ae91e5; }
QPushButton:hover, QToolButton:hover { background: #303749; border-color: #777292; }
QPushButton:pressed, QToolButton:pressed { background: #3d3457; }
QPushButton:checked, QToolButton:checked { background: #352b50; border-color: #9c7fe3; color: #e4d8ff; }
QPushButton#primary, QToolButton#primary { background: #8056d9; border-color: #ac89f2; color: white; font-weight: 600; }
QPushButton#primary:hover, QToolButton#primary:hover { background: #9569ef; }
QPushButton:disabled, QToolButton:disabled { color: #5f687c; background: #191e29; border-color: #252c3b; }
QToolButton::menu-button { border-left: 1px solid #534369; width: 18px; }
QToolButton::menu-indicator { subcontrol-position: right center; }
QLineEdit, QSpinBox, QComboBox, QTextEdit { background: #0d1017; border: 1px solid #343b50; border-radius: 7px; padding: 8px; selection-background-color: #7856bd; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus { border-color: #a58acb; }
QSpinBox { padding-right: 24px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 20px; background: #293043; border-top-right-radius: 7px; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; background: #293043; border-bottom-right-radius: 7px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #4a3a64; }
QListWidget { background: #11141c; border: 0; border-radius: 10px; padding: 4px; outline: none; }
QListWidget::item { background: #1b202d; border: 1px solid #2b3244; border-radius: 10px; padding: 10px; }
QListWidget::item:selected { background: #302940; border: 1px solid #a080e2; }
QListWidget::item:hover { background: #252a3a; }
QMenu { background: #202534; border: 1px solid #41495f; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 9px 26px 9px 12px; border-radius: 5px; }
QMenu::item:selected { background: #473660; }
QMenu::separator { height: 1px; background: #3a4155; margin: 6px; }
QScrollArea, QGraphicsView { border: 0; background: transparent; }
QScrollBar:vertical { background: #151a24; width: 10px; margin: 0; }
QScrollBar:horizontal { background: #151a24; height: 10px; margin: 0; }
QScrollBar::handle { background: #4f5470; border-radius: 5px; min-height: 24px; min-width: 24px; }
QScrollBar::handle:hover { background: #8a78ab; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QStatusBar { color: #8f9bb2; background: #11141c; font-size: 11px; }
QCheckBox { spacing: 8px; padding: 4px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #65647d; border-radius: 4px; background: #151923; }
QCheckBox::indicator:checked { background: #a183e8; border-color: #ccb6ff; }
QTabWidget::pane { border: 0; padding-top: 10px; }
QTabBar::tab { background: transparent; border-bottom: 2px solid transparent; padding: 10px 18px; color: #929eb6; }
QTabBar::tab:selected { color: #dfceff; border-bottom-color: #ad8ae9; }
QTabBar::tab:hover { color: #ffffff; }
QWidget#appHeader { background: #1a1f2b; border: 1px solid #2b3346; border-radius: 12px; }
QToolButton#brand { background: transparent; border: 0; font-size: 19px; font-weight: 700; padding: 3px 12px 3px 2px; color: #e4d7ff; }
QToolButton#brand:hover { background: #2d2b43; }
QToolButton#workspaceTab { background: transparent; border: 1px solid transparent; color: #9da8bd; }
QToolButton#workspaceTab:checked { background: #303346; border-color: #47475e; color: #ffffff; }
QToolButton#quickToggle { background: #202a34; border-color: #3e5a60; color: #afccd3; }
QToolButton#quickToggle:checked { background: #244c48; border-color: #76c8af; color: #c5ffe9; }
QWidget#recoveryBanner { background: #1a3034; border: 1px solid #375b61; border-radius: 8px; }
QWidget#recoveryBanner QLabel { background: transparent; color: #c5eee5; }
QWidget#quickPreview { background: #1a2030; border: 1px solid #8b6fb9; border-radius: 12px; }
QWidget#toolRail, QWidget#contextBar { background: #1a1f2b; border: 1px solid #2b3346; border-radius: 10px; }
QLabel#railHeading { background: transparent; color: #8290aa; font-size: 9px; font-weight: 600; padding: 3px 2px; }
QToolButton#annotationTool { background: transparent; border: 1px solid transparent; padding: 4px 1px; font-size: 10px; }
QToolButton#annotationTool:hover { background: #2a3041; border-color: #4e4c66; }
QToolButton#annotationTool:checked { background: #3c2f5d; border-color: #ab88e9; color: #eee3ff; }
QLabel#toolName { background: transparent; font-weight: 600; color: #d1bdf2; padding: 0 4px; }
QLabel#muted { color: #9aa8bd; background: transparent; }
QLabel#sectionTitle { font-size: 21px; font-weight: 600; color: #eee7ff; }
QWidget#welcomeCard { background: #1d2232; border: 1px solid #3b3552; border-radius: 14px; }
QWidget#welcomeCard QLabel { background: transparent; }
QLabel#welcomeTitle { font-size: 23px; font-weight: 600; color: #e1d2ff; }
QLabel#emptyState { color: #98a5bb; font-size: 15px; padding: 30px; }
QToolButton#saveStatus { border: 0; background: transparent; color: #a8d8be; text-align: left; padding-left: 2px; }
QWidget#warningBanner { background: #3c2a24; border: 1px solid #96633d; border-radius: 8px; }
QWidget#warningBanner QLabel { background: transparent; color: #ffd5aa; }
QWidget#ocrPanel { background: #1a1f2b; border: 1px solid #3d3554; border-radius: 10px; }
QWidget#ocrPanel QLabel, QWidget#ocrPanel QCheckBox { background: transparent; }
QLabel#ocrHeading { font-size: 18px; font-weight: 600; color: #ceb8fa; }
QTextEdit#ocrTextEditor { background: #0d1017; border-color: #49405e; selection-background-color: #7950c7; }
QSplitter#editorSplitter::handle { background: #463655; border-radius: 3px; margin: 4px 2px; }
QSplitter#editorSplitter::handle:hover { background: #b79af2; }
QToolTip { background: #2b283e; color: #fff; border: 1px solid #8871ac; padding: 7px; }
"""
STYLE += '\nQSpinBox::up-arrow { width: 10px; height: 10px; image: url("' + resource('chevron-up.svg').as_posix() + '"); }'
STYLE += '\nQSpinBox::down-arrow { width: 10px; height: 10px; image: url("' + resource('chevron-down.svg').as_posix() + '"); }'
STYLE += '\nQCheckBox::indicator:checked { image: url("' + resource('check.svg').as_posix() + '"); }'
