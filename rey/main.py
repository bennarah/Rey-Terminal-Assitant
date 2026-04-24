import sys
import os
import signal
from dotenv import load_dotenv
import anthropic
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt, QTimer, QEvent, QPoint, QThread, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont

load_dotenv()

# Set up Anthropic client once at startup
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are Rey, a friendly golden retriever who helps beginner programmers
with terminal and command-line questions. Keep answers short, warm, and encouraging.
Always show the exact command they need in a code block. Explain what it does in plain English.
If a question isn't about the terminal or command line, gently let them know that's
your specialty and suggest they try a search engine for other topics.
Never be condescending — everyone starts somewhere!"""


# ---------------------------------------------------------------------------
# Background thread for Gemini API calls (keeps UI responsive)
# ---------------------------------------------------------------------------

class AskReyThread(QThread):
    response_ready = Signal(str)   # emits the answer when done
    error_occurred = Signal(str)   # emits error message if something goes wrong

    def __init__(self, question):
        super().__init__()
        self.question = question

    def run(self):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": self.question}]
            )
            self.response_ready.emit(message.content[0].text)
        except Exception as e:
            self.error_occurred.emit(f"Oops, something went wrong: {str(e)}")


# ---------------------------------------------------------------------------
# Chat popup window
# ---------------------------------------------------------------------------

class ChatPopup(QWidget):
    def __init__(self, parent_x, parent_y):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(340, 420)

        self.move(max(0, parent_x - 140), parent_y - 430)
        self._build_ui()
        self.show()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget(self)
        card.setObjectName("card")
        card.setStyleSheet("""
            QWidget#card {
                background-color: #1e1e2e;
                border-radius: 16px;
                border: 1.5px solid #444466;
            }
        """)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # --- Title bar ---
        title_row = QHBoxLayout()
        title = QLabel("Rey 🐾")
        title.setStyleSheet("color: #f0c060; font-weight: bold; font-size: 14px;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #444466; color: #aaaacc;
                border: none; border-radius: 11px; font-size: 11px;
            }
            QPushButton:hover { background: #cc4455; color: white; }
        """)
        close_btn.clicked.connect(self.close)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        # --- Chat display ---
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #13131f;
                color: #e0e0f0;
                border: none;
                border-radius: 10px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        self.chat_display.setFont(QFont("Menlo", 12))
        self.chat_display.setText("Woof! Ask me anything about the terminal. 🐾\n")
        layout.addWidget(self.chat_display)

        # --- Input row ---
        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("e.g. how do I clone a repo?")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #13131f;
                color: #e0e0f0;
                border: 1.5px solid #444466;
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1.5px solid #f0c060; }
        """)
        self.input_field.returnPressed.connect(self.send_message)

        self.send_btn = QPushButton("Ask")
        self.send_btn.setFixedWidth(50)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0c060;
                color: #1e1e2e;
                border: none;
                border-radius: 10px;
                font-weight: bold;
                font-size: 12px;
                padding: 6px;
            }
            QPushButton:hover { background-color: #ffd880; }
            QPushButton:disabled { background-color: #555555; color: #999999; }
        """)
        self.send_btn.clicked.connect(self.send_message)

        input_row.addWidget(self.input_field)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

        self.input_field.setFocus()
        self.ai_thread = None  # track the background thread

    def send_message(self):
        question = self.input_field.text().strip()
        if not question:
            return

        # Disable input while waiting for Rey's response
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)

        self.chat_display.append(f"You: {question}\n")
        self.chat_display.append("Rey is thinking... 🐾\n")

        # Fire off the API call in a background thread
        self.ai_thread = AskReyThread(question)
        self.ai_thread.response_ready.connect(self.on_response)
        self.ai_thread.error_occurred.connect(self.on_error)
        self.ai_thread.start()

    def on_response(self, text):
        """Called when Gemini responds — runs back on the main thread."""
        # Remove the "thinking" line
        cursor = self.chat_display.textCursor()
        content = self.chat_display.toPlainText()
        content = content.replace("Rey is thinking... 🐾\n", "")
        self.chat_display.setPlainText(content)
        self.chat_display.append(f"Rey: {text}\n")

        # Scroll to bottom
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )

        # Re-enable input
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_field.setFocus()

    def on_error(self, message):
        self.chat_display.toPlainText().replace("Rey is thinking... 🐾\n", "")
        self.chat_display.append(f"Rey: {message}\n")
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_field.setFocus()


# ---------------------------------------------------------------------------
# Main walking window
# ---------------------------------------------------------------------------

class ReyWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen().geometry()
        self.screen_width = screen.width()
        self.screen_height = screen.height()

        self.rey_width = 64
        self.rey_height = 64
        self.dock_height = 40

        win_height = self.rey_height + 20
        self.setGeometry(
            0,
            self.screen_height - self.dock_height - win_height,
            self.screen_width,
            win_height
        )

        self.rey_x = 0
        self.direction = 1
        self.speed = 1
        self.chat_popup = None

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_position)
        self.timer.start(16)

        self.show()

    def update_position(self):
        self.rey_x += self.speed * self.direction
        if self.rey_x >= self.screen_width - self.rey_width:
            self.direction = -1
        elif self.rey_x <= 0:
            self.direction = 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QBrush(QColor(220, 160, 60)))
        painter.setPen(QPen(QColor(180, 120, 30), 2))
        painter.drawRoundedRect(
            int(self.rey_x), 10,
            self.rey_width, self.rey_height,
            10, 10
        )

        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(
            int(self.rey_x), 10,
            self.rey_width, self.rey_height,
            Qt.AlignmentFlag.AlignCenter,
            "Rey 🐾"
        )

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self.show()
            self.raise_()
        super().changeEvent(event)

    def mousePressEvent(self, event):
        click_x = event.position().x()
        if not (self.rey_x <= click_x <= self.rey_x + self.rey_width):
            return

        if self.chat_popup and self.chat_popup.isVisible():
            self.chat_popup.close()
            self.chat_popup = None
        else:
            win_pos = self.mapToGlobal(QPoint(int(self.rey_x), 0))
            self.chat_popup = ChatPopup(win_pos.x(), win_pos.y())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    window = ReyWindow()
    sys.exit(app.exec())
