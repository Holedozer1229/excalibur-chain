"""main.py — Kivy-based AetherionEXCAL wallet application.

Full-featured mobile/desktop wallet with screens for:
- Dashboard: chain height, mempool, peers, mining status
- Wallet: create, import, view address, check balance
- Send: build and broadcast transactions
- Receive: show receive address with QR code
- Explorer: block and transaction browsing
- Locks: HTLC/QHTLC operations
- Settings: RPC endpoint, network, data directory

Run:
    python -m kivy_wallet
    or
    python kivy_wallet/main.py

Build for Android (Buildozer):
    buildozer android debug

Build for iOS (Kivy-iOS):
    kivy-ios toolchain build kivy
"""
import os
import sys
import threading
import time
from datetime import datetime

# Kivy imports
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.popup import Popup
from kivy.uix.gridlayout import GridLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.progressbar import ProgressBar
from kivy.uix.switch import Switch
from kivy.uix.spinner import Spinner
from kivy.uix.cardview import Card
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivy.uix.label import Label as KivyLabel
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.config import Config
from kivy.utils import get_color_from_hex
from kivy.properties import StringProperty, NumericProperty, ListProperty, ObjectProperty

# Set Kivy config before importing graphics
Config.set('graphics', 'resizable', '1')
Config.set('graphics', 'width', '400')
Config.set('graphics', 'height', '700')

# Project imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from .rpc_client import RpcClient, RpcError
from .wallet_manager import WalletManager, WalletManagerError


# ─── Color Palette (matching excal_wallet.py) ─────────────────────────

COLORS = {
    "bg_dark":        get_color_from_hex("#0a0a1a"),
    "bg_panel":       get_color_from_hex("#0d0d2b"),
    "bg_card":        get_color_from_hex("#111133"),
    "bg_input":       get_color_from_hex("#1a1a44"),
    "accent_gold":    get_color_from_hex("#FFD700"),
    "accent_cyan":    get_color_from_hex("#00E5FF"),
    "accent_purple":  get_color_from_hex("#B388FF"),
    "accent_green":   get_color_from_hex("#00E676"),
    "accent_red":     get_color_from_hex("#FF4081"),
    "text_primary":   get_color_from_hex("#FFFFFF"),
    "text_secondary": get_color_from_hex("#B0B0D0"),
    "text_dim":       get_color_from_hex("#6060A0"),
    "border":         get_color_from_hex("#2a2a5a"),
}


# ─── Reusable Widgets ──────────────────────────────────────────────────

class ExcalButton(Button):
    """Styled button matching the Aetherion theme."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = COLORS["bg_card"]
        self.color = COLORS["accent_gold"]
        self.font_size = "16sp"
        self.bold = True
        self.size_hint_y = None
        self.height = 50


class ExcalInput(TextInput):
    """Styled text input matching the Aetherion theme."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = COLORS["bg_input"]
        self.foreground_color = COLORS["text_primary"]
        self.font_size = "16sp"
        self.hint_text_color = COLORS["text_dim"]
        self.size_hint_y = None
        self.height = 50


class StatCard(BoxLayout):
    """A card showing a single stat (label + value)."""

    def __init__(self, title="", value="", accent=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.height = 80
        self.padding = [10, 10]
        self.spacing = 5

        title_label = Label(
            text=title,
            color=COLORS["text_secondary"],
            font_size="13sp",
            halign="left",
            size_hint_y=None,
            height=25,
        )
        value_label = Label(
            text=str(value),
            color=accent or COLORS["accent_gold"],
            font_size="20sp",
            bold=True,
            halign="left",
        )

        self.add_widget(title_label)
        self.add_widget(value_label)

    def update_value(self, value):
        for child in self.children:
            if isinstance(child, Label) and child.bold:
                child.text = str(value)


class SectionLabel(Label):
    """Section header label."""

    def __init__(self, text="", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.color = COLORS["accent_cyan"]
        self.font_size = "15sp"
        self.bold = True
        self.size_hint_y = None
        self.height = 30
        self.halign = "left"


# ─── Screens ───────────────────────────────────────────────────────────

class DashboardScreen(Screen):
    """Main dashboard: chain status, network, mempool."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "dashboard"
        self.rpc_client = None
        self._refresh_handle = None
        self.build_ui()

    def build_ui(self):
        layout = BoxLayout(orientation="vertical", padding=[10, 10], spacing=10)
        layout.canvas.before.do_color = lambda c: c.setter('rgba', COLORS["bg_dark"])

        # Header
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=50)
        header.add_widget(Label(
            text="AetherionEXCAL",
            color=COLORS["accent_gold"],
            font_size="20sp",
            bold=True,
            halign="left",
        ))
        self.status_label = Label(
            text="● Connected",
            color=COLORS["accent_green"],
            font_size="14sp",
            halign="right",
        )
        header.add_widget(self.status_label)
        layout.add_widget(header)

        # Stats grid
        stats_grid = GridLayout(cols=2, spacing=8, size_hint_y=None)
        stats_grid.bind(minimum_height=stats_grid.setter('height'))

        self.height_card = StatCard("Chain Height", "—")
        self.peers_card = StatCard("Peers", "—")
        self.mempool_card = StatCard("Mempool", "—")
        self.best_hash_card = StatCard("Best Block", "—")

        for card in [self.height_card, self.peers_card,
                     self.mempool_card, self.best_hash_card]:
            stats_grid.add_widget(card)

        layout.add_widget(stats_grid)

        # Block time and tips
        self.block_time_label = Label(
            text="Last block: —",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=30,
        )
        layout.add_widget(self.block_time_label)

        # Peer list scroll
        SectionLabel(text="Connected Peers")
        layout.add_widget(SectionLabel(text="Connected Peers"))

        peer_scroll = ScrollView()
        self.peer_list = BoxLayout(orientation="vertical", size_hint_y=None, spacing=5)
        self.peer_list.bind(minimum_height=self.peer_list.setter('height'))
        peer_scroll.add_widget(self.peer_list)
        layout.add_widget(peer_scroll)

        # Refresh button
        refresh_btn = ExcalButton(text="⟳ Refresh")
        refresh_btn.bind(on_press=self.refresh)
        layout.add_widget(refresh_btn)

        self.add_widget(layout)

    def on_enter(self):
        """Start auto-refresh when entering the screen."""
        self.refresh()
        self._refresh_handle = Clock.schedule_interval(self._auto_refresh, 30)

    def on_leave(self):
        """Stop auto-refresh when leaving."""
        if self._refresh_handle:
            self._refresh_handle.cancel()
            self._refresh_handle = None

    def _auto_refresh(self, dt):
        self._do_refresh()

    def refresh(self, instance=None):
        self._do_refresh()

    def _do_refresh(self):
        app = ExcalWalletApp.instance()
        if not app:
            return
        client = app.rpc_client
        if not client:
            return

        try:
            status = client.get_status()
            self.status_label.text = "● Connected"
            self.status_label.color = COLORS["accent_green"]

            if status["height"] is not None:
                self.height_card.update_value(str(status["height"]))
            if status["best_hash"]:
                short_hash = status["best_hash"][:16] + "…"
                self.best_hash_card.update_value(short_hash)
            if status["peer_count"] is not None:
                self.peers_card.update_value(str(status["peer_count"]))
            if status["mempool"]:
                mp_size = status["mempool"].get("size", 0)
                self.mempool_card.update_value(str(mp_size))

            # Update peer list
            self.peer_list.clear_widgets()
            for peer in status.get("peers", [])[:10]:
                peer_label = Label(
                    text=f"  {peer.get('addr', 'unknown')} — height: {peer.get('height', '?')}",
                    color=COLORS["text_secondary"],
                    font_size="12sp",
                    size_hint_y=None,
                    height=25,
                    halign="left",
                )
                self.peer_list.add_widget(peer_label)

            if not status.get("peers"):
                empty = Label(
                    text="  No peers connected",
                    color=COLORS["text_dim"],
                    font_size="12sp",
                    size_hint_y=None,
                    height=25,
                    halign="left",
                )
                self.peer_list.add_widget(empty)

        except RpcError as e:
            self.status_label.text = "● Disconnected"
            self.status_label.color = COLORS["accent_red"]
            self.height_card.update_value("Error")


class WalletScreen(Screen):
    """Wallet management: create, load, view balance, addresses."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "wallet"
        self.build_ui()

    def build_ui(self):
        layout = BoxLayout(orientation="vertical", padding=[10, 10], spacing=10)

        # Header
        layout.add_widget(Label(
            text="Wallet",
            color=COLORS["accent_gold"],
            font_size="20sp",
            bold=True,
            size_hint_y=None,
            height=40,
            halign="left",
        ))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=10, padding=[0, 10])
        content.bind(minimum_height=content.setter('height'))

        # Status
        self.wallet_status = Label(
            text="No wallet loaded",
            color=COLORS["text_dim"],
            font_size="14sp",
            size_hint_y=None,
            height=30,
        )
        content.add_widget(self.wallet_status)

        # Balance section
        SectionLabel(text="Balance")
        content.add_widget(SectionLabel(text="Balance"))
        self.balance_label = Label(
            text="0.00000000 EXCAL",
            color=COLORS["accent_gold"],
            font_size="24sp",
            bold=True,
            size_hint_y=None,
            height=50,
        )
        content.add_widget(self.balance_label)
        self.utxo_label = Label(
            text="0 UTXOs",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=25,
        )
        content.add_widget(self.utxo_label)

        # Address section
        SectionLabel(text="Receive Address")
        content.add_widget(SectionLabel(text="Receive Address"))
        self.address_label = Label(
            text="—",
            color=COLORS["accent_cyan"],
            font_size="12sp",
            size_hint_y=None,
            height=40,
            halign="left",
        )
        content.add_widget(self.address_label)

        # Mnemonic section (shown after creation)
        self.mnemonic_section = BoxLayout(orientation="vertical", size_hint_y=None, spacing=5)
        self.mnemonic_section.height = 0
        self.mnemonic_label = Label(
            text="",
            color=COLORS["accent_purple"],
            font_size="12sp",
            bold=True,
            size_hint_y=None,
            height=60,
        )
        self.mnemonic_section.add_widget(Label(
            text="⚠ BACKUP THIS PHRASE — shown once:",
            color=COLORS["accent_red"],
            font_size="12sp",
            bold=True,
            size_hint_y=None,
            height=25,
        ))
        self.mnemonic_section.add_widget(self.mnemonic_label)
        content.add_widget(self.mnemonic_section)

        # Actions
        actions = GridLayout(cols=2, spacing=5, size_hint_y=None, height=110)

        create_btn = ExcalButton(text="Create New")
        create_btn.bind(on_press=self.show_create_dialog)
        actions.add_widget(create_btn)

        load_btn = ExcalButton(text="Load Existing")
        load_btn.bind(on_press=self.show_load_dialog)
        actions.add_widget(load_btn)

        import_btn = ExcalButton(text="Import Seed")
        import_btn.bind(on_press=self.show_import_dialog)
        actions.add_widget(import_btn)

        refresh_btn = ExcalButton(text="⟳ Refresh")
        refresh_btn.bind(on_press=self.refresh_balance)
        actions.add_widget(refresh_btn)

        content.add_widget(actions)

        scroll.add_widget(content)
        layout.add_widget(scroll)
        self.add_widget(layout)

    def on_enter(self):
        self.refresh_balance()

    def refresh_balance(self, instance=None):
        app = ExcalWalletApp.instance()
        if not app or not app.wallet_mgr.is_loaded:
            self.wallet_status.text = "No wallet loaded"
            self.wallet_status.color = COLORS["text_dim"]
            self.balance_label.text = "0.00000000 EXCAL"
            self.address_label.text = "—"
            return

        self.wallet_status.text = "Wallet loaded"
        self.wallet_status.color = COLORS["accent_green"]

        try:
            balance = app.wallet_mgr.get_balance(app.rpc_url)
            self.balance_label.text = f"{balance['excal']:.8f} EXCAL"
            self.utxo_label.text = f"{balance['utxo_count']} UTXOs"
        except WalletManagerError as e:
            self.balance_label.text = f"Error: {e}"
            self.balance_label.color = COLORS["accent_red"]

        try:
            addr = app.wallet_mgr.get_receive_address()
            self.address_label.text = addr
        except WalletManagerError:
            pass

    def show_create_dialog(self, instance=None):
        content = BoxLayout(orientation="vertical", spacing=10, padding=[10, 10])

        content.add_widget(Label(
            text="Create new wallet",
            color=COLORS["accent_gold"],
            font_size="16sp",
            bold=True,
            size_hint_y=None,
            height=30,
        ))

        content.add_widget(Label(
            text="Passphrase (encrypts wallet at rest):",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=25,
        ))
        pw_input = ExcalInput(hint_text="Passphrase", password=True)
        content.add_widget(pw_input)

        content.add_widget(Label(
            text="Confirm passphrase:",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=25,
        ))
        pw2_input = ExcalInput(hint_text="Confirm passphrase", password=True)
        content.add_widget(pw2_input)

        words_spinner = Spinner(
            text="12",
            values=["12", "24"],
            size_hint_y=None,
            height=40,
        )
        content.add_widget(Label(
            text="Mnemonic words:",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=25,
        ))
        content.add_widget(words_spinner)

        def do_create(instance):
            if pw_input.text != pw2_input.text:
                self.show_error("Passphrases do not match")
                return
            if not pw_input.text:
                self.show_error("Passphrase required")
                return
            try:
                words = int(words_spinner.text)
                mnemonic = app.wallet_mgr.create_wallet(pw_input.text, mnemonic_words=words)
                self.mnemonic_label.text = mnemonic
                self.mnemonic_section.height = 120
                self.show_info("Wallet created! Backup your mnemonic phrase.")
                self.refresh_balance()
                popup.dismiss()
            except WalletManagerError as e:
                self.show_error(str(e))

        btn_layout = GridLayout(cols=2, spacing=5, size_hint_y=None, height=50)
        ok_btn = ExcalButton(text="Create")
        ok_btn.bind(on_press=do_create)
        cancel_btn = ExcalButton(text="Cancel")
        cancel_btn.bind(on_press=lambda x: popup.dismiss())
        btn_layout.add_widget(ok_btn)
        btn_layout.add_widget(cancel_btn)
        content.add_widget(btn_layout)

        popup = Popup(title="Create Wallet", content=content,
                      size_hint=(0.9, 0.8), auto_dismiss=False)
        popup.open()

    def show_load_dialog(self, instance=None):
        app = ExcalWalletApp.instance()
        if not app:
            return

        content = BoxLayout(orientation="vertical", spacing=10, padding=[10, 10])
        content.add_widget(Label(
            text="Load existing wallet",
            color=COLORS["accent_gold"],
            font_size="16sp",
            bold=True,
            size_hint_y=None,
            height=30,
        ))

        pw_input = ExcalInput(hint_text="Passphrase", password=True)
        content.add_widget(pw_input)

        def do_load(instance):
            try:
                app.wallet_mgr.load_wallet(pw_input.text)
                self.show_info("Wallet loaded successfully")
                self.refresh_balance()
                popup.dismiss()
            except WalletManagerError as e:
                self.show_error(str(e))

        btn_layout = GridLayout(cols=2, spacing=5, size_hint_y=None, height=50)
        ok_btn = ExcalButton(text="Load")
        ok_btn.bind(on_press=do_load)
        cancel_btn = ExcalButton(text="Cancel")
        cancel_btn.bind(on_press=lambda x: popup.dismiss())
        btn_layout.add_widget(ok_btn)
        btn_layout.add_widget(cancel_btn)
        content.add_widget(btn_layout)

        popup = Popup(title="Load Wallet", content=content,
                      size_hint=(0.9, 0.5), auto_dismiss=False)
        popup.open()

    def show_import_dialog(self, instance=None):
        content = BoxLayout(orientation="vertical", spacing=10, padding=[10, 10])
        content.add_widget(Label(
            text="Import from seed phrase",
            color=COLORS["accent_gold"],
            font_size="16sp",
            bold=True,
            size_hint_y=None,
            height=30,
        ))

        content.add_widget(Label(
            text="BIP-39 mnemonic (12 or 24 words):",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=25,
        ))
        seed_input = ExcalInput(
            hint_text="word1 word2 word3 ...",
            multiline=False,
        )
        content.add_widget(seed_input)

        pw_input = ExcalInput(hint_text="New passphrase", password=True)
        content.add_widget(pw_input)

        def do_import(instance):
            try:
                app = ExcalWalletApp.instance()
                app.wallet_mgr.import_wallet(pw_input.text, seed_input.text)
                self.show_info("Wallet imported successfully")
                self.refresh_balance()
                popup.dismiss()
            except WalletManagerError as e:
                self.show_error(str(e))

        btn_layout = GridLayout(cols=2, spacing=5, size_hint_y=None, height=50)
        ok_btn = ExcalButton(text="Import")
        ok_btn.bind(on_press=do_import)
        cancel_btn = ExcalButton(text="Cancel")
        cancel_btn.bind(on_press=lambda x: popup.dismiss())
        btn_layout.add_widget(ok_btn)
        btn_layout.add_widget(cancel_btn)
        content.add_widget(btn_layout)

        popup = Popup(title="Import Wallet", content=content,
                      size_hint=(0.9, 0.6), auto_dismiss=False)
        popup.open()

    def show_error(self, message):
        content = BoxLayout(orientation="vertical", spacing=10, padding=[20, 20])
        content.add_widget(Label(
            text=message,
            color=COLORS["accent_red"],
            font_size="14sp",
        ))
        ok_btn = ExcalButton(text="OK")
        ok_btn.bind(on_press=lambda x: popup.dismiss())
        content.add_widget(ok_btn)
        popup = Popup(title="Error", content=content, size_hint=(0.8, 0.3))
        popup.open()

    def show_info(self, message):
        content = BoxLayout(orientation="vertical", spacing=10, padding=[20, 20])
        content.add_widget(Label(
            text=message,
            color=COLORS["accent_green"],
            font_size="14sp",
        ))
        ok_btn = ExcalButton(text="OK")
        ok_btn.bind(on_press=lambda x: popup.dismiss())
        content.add_widget(ok_btn)
        popup = Popup(title="Info", content=content, size_hint=(0.8, 0.3))
        popup.open()


class SendScreen(Screen):
    """Send EXCAL to an address."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "send"
        self.build_ui()

    def build_ui(self):
        layout = BoxLayout(orientation="vertical", padding=[10, 10], spacing=10)

        layout.add_widget(Label(
            text="Send EXCAL",
            color=COLORS["accent_gold"],
            font_size="20sp",
            bold=True,
            size_hint_y=None,
            height=40,
            halign="left",
        ))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=10, padding=[0, 10])
        content.bind(minimum_height=content.setter('height'))

        # Recipient
        content.add_widget(Label(
            text="Recipient address (PKH lock hex):",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=25,
        ))
        self.to_input = ExcalInput(hint_text="00" + "a" * 40)
        content.add_widget(self.to_input)

        # Amount
        content.add_widget(Label(
            text="Amount (EXCAL):",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=25,
        ))
        self.amount_input = ExcalInput(hint_text="0.01", keyboard_mode="numbers")
        content.add_widget(self.amount_input)

        # Fee rate
        content.add_widget(Label(
            text="Fee rate (swords/vbyte):",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=25,
        ))
        self.fee_input = ExcalInput(hint_text="1", text="1", keyboard_mode="numbers")
        content.add_widget(self.fee_input)

        # Preview
        self.preview_label = Label(
            text="",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=60,
        )
        content.add_widget(self.preview_label)

        # Send button
        self.send_btn = ExcalButton(text="Build & Send")
        self.send_btn.bind(on_press=self.do_send)
        content.add_widget(self.send_btn)

        # Result
        self.result_label = Label(
            text="",
            color=COLORS["accent_green"],
            font_size="13sp",
            bold=True,
            size_hint_y=None,
            height=40,
        )
        content.add_widget(self.result_label)

        scroll.add_widget(content)
        layout.add_widget(scroll)
        self.add_widget(layout)

    def do_send(self, instance=None):
        app = ExcalWalletApp.instance()
        if not app or not app.wallet_mgr.is_loaded:
            self.result_label.text = "Error: No wallet loaded"
            self.result_label.color = COLORS["accent_red"]
            return

        to_addr = self.to_input.text.strip()
        try:
            amount = float(self.amount_input.text)
        except ValueError:
            self.result_label.text = "Error: Invalid amount"
            self.result_label.color = COLORS["accent_red"]
            return

        try:
            fee_rate = int(self.fee_input.text)
        except ValueError:
            fee_rate = 1

        try:
            # Build transaction
            tx_result = app.wallet_mgr.build_send_tx(to_addr, amount, fee_rate)
            tx_hex = tx_result.get("tx_hex", "")

            # Broadcast
            txid = app.rpc_client.sendrawtransaction(tx_hex)
            self.result_label.text = f"Sent! TXID: {txid[:20]}…"
            self.result_label.color = COLORS["accent_green"]
            self.preview_label.text = f"TX hex: {tx_hex[:60]}…"

        except (WalletManagerError, RpcError) as e:
            self.result_label.text = f"Error: {e}"
            self.result_label.color = COLORS["accent_red"]


class ReceiveScreen(Screen):
    """Show receive address for incoming payments."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "receive"
        self.build_ui()

    def build_ui(self):
        layout = BoxLayout(orientation="vertical", padding=[10, 10], spacing=15)

        layout.add_widget(Label(
            text="Receive EXCAL",
            color=COLORS["accent_gold"],
            font_size="20sp",
            bold=True,
            size_hint_y=None,
            height=40,
            halign="left",
        ))

        # Address display
        layout.add_widget(Label(
            text="Your receive address:",
            color=COLORS["text_secondary"],
            font_size="14sp",
            size_hint_y=None,
            height=25,
        ))

        self.address_display = Label(
            text="—",
            color=COLORS["accent_cyan"],
            font_size="13sp",
            size_hint_y=None,
            height=80,
            halign="left",
            valign="middle",
        )
        layout.add_widget(self.address_display)

        # Copy button
        copy_btn = ExcalButton(text="Copy Address")
        copy_btn.bind(on_press=self.copy_address)
        layout.add_widget(copy_btn)

        # New address button
        new_btn = ExcalButton(text="Generate New Address")
        new_btn.bind(on_press=self.new_address)
        layout.add_widget(new_btn)

        # Info
        info = Label(
            text="Share this address to receive EXCAL.\n"
                 "Each address is derived from your seed —\n"
                 "no need to back them up separately.",
            color=COLORS["text_dim"],
            font_size="12sp",
        )
        layout.add_widget(info)

        self.add_widget(layout)

    def on_enter(self):
        self.show_address()

    def show_address(self):
        app = ExcalWalletApp.instance()
        if not app or not app.wallet_mgr.is_loaded:
            self.address_display.text = "No wallet loaded"
            return
        try:
            addr = app.wallet_mgr.get_receive_address()
            self.address_display.text = addr
        except WalletManagerError:
            self.address_display.text = "Error loading address"

    def copy_address(self, instance=None):
        from kivy.core.clipboard import Clipboard
        Clipboard.put_multipart([self.address_display.text.encode()])

    def new_address(self, instance=None):
        self.show_address()


class ExplorerScreen(Screen):
    """Block explorer: browse blocks and transactions."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "explorer"
        self.build_ui()

    def build_ui(self):
        layout = BoxLayout(orientation="vertical", padding=[10, 10], spacing=10)

        layout.add_widget(Label(
            text="Block Explorer",
            color=COLORS["accent_gold"],
            font_size="20sp",
            bold=True,
            size_hint_y=None,
            height=40,
            halign="left",
        ))

        # Search
        search_layout = BoxLayout(orientation="horizontal", spacing=5, size_hint_y=None, height=55)
        self.search_input = ExcalInput(hint_text="Block hash or height")
        search_layout.add_widget(self.search_input)
        search_btn = ExcalButton(text="Search")
        search_btn.size_hint_x = 0.3
        search_btn.bind(on_press=self.search_block)
        search_layout.add_widget(search_btn)
        layout.add_widget(search_layout)

        # Block details
        self.block_info = Label(
            text="Search for a block to view details",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=200,
        )
        layout.add_widget(self.block_info)

        # Tips
        tips_btn = ExcalButton(text="Show Chain Tips")
        tips_btn.bind(on_press=self.show_tips)
        layout.add_widget(tips_btn)

        self.add_widget(layout)

    def search_block(self, instance=None):
        app = ExcalWalletApp.instance()
        if not app:
            return

        query = self.search_input.text.strip()
        if not query:
            return

        try:
            client = app.rpc_client
            # Try as hash first
            if len(query) == 64:
                block = client.getblock(query)
            else:
                # Try as height — get best block and walk back
                try:
                    height = int(query)
                    best_hash = client.getbestblockhash()
                    best = client.getblock(best_hash)
                    best_height = best["height"]
                    if height > best_height:
                        self.block_info.text = f"Height {height} not yet reached (tip: {best_height})"
                        return
                    # For simplicity, just show the best block
                    block = best
                    self.block_info.text = (
                        f"Note: Showing tip block (height {best_height}).\n"
                        f"Full height lookup requires chain index.\n\n"
                    ) + self._format_block(block)
                    return
                except ValueError:
                    self.block_info.text = f"Not found: {query}"
                    return

            self.block_info.text = self._format_block(block)

        except RpcError as e:
            self.block_info.text = f"Error: {e}"
            self.block_info.color = COLORS["accent_red"]

    def show_tips(self, instance=None):
        app = ExcalWalletApp.instance()
        if not app:
            return

        try:
            tips = app.rpc_client.getchaintips()
            lines = ["Chain Tips:"]
            for tip in tips:
                lines.append(
                    f"  Height: {tip['height']}\n"
                    f"  Hash:   {tip['hash']}\n"
                    f"  Work:   {tip['work']}\n"
                )
            self.block_info.text = "\n".join(lines)
            self.block_info.color = COLORS["text_secondary"]
        except RpcError as e:
            self.block_info.text = f"Error: {e}"
            self.block_info.color = COLORS["accent_red"]

    def _format_block(self, block: dict) -> str:
        lines = [
            f"Block Details:",
            f"  Height:          {block.get('height', '?')}",
            f"  Hash:            {block.get('hash', '?')}",
            f"  Confirmations:   {block.get('confirmations', '?')}",
            f"  Version:         {block.get('version', '?')}",
            f"  Previous:        {block.get('prev', '?')[:20]}…",
            f"  Merkle Root:     {block.get('merkle', '?')[:20]}…",
            f"  Time:            {block.get('time', '?')}",
            f"  Bits:            {block.get('bits', '?')}",
            f"  Nonce:           {block.get('nonce', '?')}",
            f"  Transactions:    {len(block.get('tx', []))}",
        ]
        txs = block.get("tx", [])
        if txs:
            lines.append("  TX IDs:")
            for tx in txs[:5]:
                lines.append(f"    - {tx[:20]}…")
            if len(txs) > 5:
                lines.append(f"    ... and {len(txs) - 5} more")
        return "\n".join(lines)


class LocksScreen(Screen):
    """HTLC and QHTLC lock operations."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "locks"
        self.build_ui()

    def build_ui(self):
        layout = BoxLayout(orientation="vertical", padding=[10, 10], spacing=10)

        layout.add_widget(Label(
            text="Lock Operations",
            color=COLORS["accent_gold"],
            font_size="20sp",
            bold=True,
            size_hint_y=None,
            height=40,
            halign="left",
        ))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=10, padding=[0, 10])
        content.bind(minimum_height=content.setter('height'))

        # HTLC section
        content.add_widget(SectionLabel(text="HTLC Lock"))
        content.add_widget(Label(
            text="Create a hash-time-locked contract.",
            color=COLORS["text_dim"],
            font_size="12sp",
            size_hint_y=None,
            height=20,
        ))

        self.htlc_hash_input = ExcalInput(hint_text="Secret hash (hex)")
        content.add_widget(self.htlc_hash_input)

        self.htlc_timeout_input = ExcalInput(hint_text="Timeout block height", text="50000")
        content.add_widget(self.htlc_timeout_input)

        self.htlc_refund_input = ExcalInput(hint_text="Refund address")
        content.add_widget(self.htlc_refund_input)

        htlc_btn = ExcalButton(text="Create HTLC Lock")
        htlc_btn.bind(on_press=self.create_htlc)
        content.add_widget(htlc_btn)

        # QHTLC section
        content.add_widget(SectionLabel(text="QHTLC Lock (Quantum-Resistant)"))
        content.add_widget(Label(
            text="Create a quantum-resistant HTLC using Trifold signatures.",
            color=COLORS["text_dim"],
            font_size="12sp",
            size_hint_y=None,
            height=20,
        ))

        self.qhtlc_hash_input = ExcalInput(hint_text="Secret hash (hex)")
        content.add_widget(self.qhtlc_hash_input)

        self.qhtlc_timeout_input = ExcalInput(hint_text="Timeout block height", text="50000")
        content.add_widget(self.qhtlc_timeout_input)

        self.qhtlc_refund_input = ExcalInput(hint_text="Refund address")
        content.add_widget(self.qhtlc_refund_input)

        qhtlc_btn = ExcalButton(text="Create QHTLC Lock")
        qhtlc_btn.bind(on_press=self.create_qhtlc)
        content.add_widget(qhtlc_btn)

        # Parse lock
        content.add_widget(SectionLabel(text="Parse Lock"))
        self.parse_lock_input = ExcalInput(hint_text="Lock hex to parse")
        content.add_widget(self.parse_lock_input)

        parse_btn = ExcalButton(text="Parse")
        parse_btn.bind(on_press=self.parse_lock)
        content.add_widget(parse_btn)

        # Result
        self.result_label = Label(
            text="",
            color=COLORS["accent_cyan"],
            font_size="12sp",
            size_hint_y=None,
            height=100,
        )
        content.add_widget(self.result_label)

        scroll.add_widget(content)
        layout.add_widget(scroll)
        self.add_widget(layout)

    def create_htlc(self, instance=None):
        app = ExcalWalletApp.instance()
        if not app:
            return
        try:
            secret_hash = bytes.fromhex(self.htlc_hash_input.text.strip())
            timeout = int(self.htlc_timeout_input.text)
            refund = self.htlc_refund_input.text.strip()

            result = app.wallet_mgr.create_htlc_lock(secret_hash, timeout, refund)
            self.result_label.text = f"HTLC Lock:\n{result['lock_hex']}"
            self.result_label.color = COLORS["accent_green"]
        except Exception as e:
            self.result_label.text = f"Error: {e}"
            self.result_label.color = COLORS["accent_red"]

    def create_qhtlc(self, instance=None):
        app = ExcalWalletApp.instance()
        if not app:
            return
        try:
            secret_hash = bytes.fromhex(self.qhtlc_hash_input.text.strip())
            timeout = int(self.qhtlc_timeout_input.text)
            refund = self.qhtlc_refund_input.text.strip()

            result = app.wallet_mgr.create_qhtlc_lock(secret_hash, timeout, refund)
            self.result_label.text = f"QHTLC Lock:\n{result['lock_hex']}"
            self.result_label.color = COLORS["accent_green"]
        except Exception as e:
            self.result_label.text = f"Error: {e}"
            self.result_label.color = COLORS["accent_red"]

    def parse_lock(self, instance=None):
        app = ExcalWalletApp.instance()
        if not app:
            return
        try:
            lock_hex = self.parse_lock_input.text.strip()
            result = app.wallet_mgr.parse_lock(lock_hex)
            self.result_label.text = (
                f"Type: {result['type']}\n"
                f"Status: {result['status']}"
            )
            self.result_label.color = COLORS["accent_cyan"]
        except Exception as e:
            self.result_label.text = f"Error: {e}"
            self.result_label.color = COLORS["accent_red"]


class SettingsScreen(Screen):
    """App settings: RPC endpoint, network, data directory."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "settings"
        self.build_ui()

    def build_ui(self):
        layout = BoxLayout(orientation="vertical", padding=[10, 10], spacing=10)

        layout.add_widget(Label(
            text="Settings",
            color=COLORS["accent_gold"],
            font_size="20sp",
            bold=True,
            size_hint_y=None,
            height=40,
            halign="left",
        ))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=10, padding=[0, 10])
        content.bind(minimum_height=content.setter('height'))

        # RPC URL
        content.add_widget(SectionLabel(text="Node Connection"))
        content.add_widget(Label(
            text="RPC endpoint URL:",
            color=COLORS["text_secondary"],
            font_size="13sp",
            size_hint_y=None,
            height=25,
        ))
        self.rpc_url_input = ExcalInput(hint_text="http://127.0.0.1:9432")
        content.add_widget(self.rpc_url_input)

        save_btn = ExcalButton(text="Save & Reconnect")
        save_btn.bind(on_press=self.save_rpc_url)
        content.add_widget(save_btn)

        # Network
        content.add_widget(SectionLabel(text="Network"))
        self.network_spinner = Spinner(
            text="fork",
            values=["fork", "mainnet", "testnet"],
            size_hint_y=None,
            height=40,
        )
        content.add_widget(self.network_spinner)

        # Data directory
        content.add_widget(SectionLabel(text="Data Directory"))
        self.datadir_input = ExcalInput(hint_text="Wallet data directory")
        content.add_widget(self.datadir_input)

        # About
        content.add_widget(SectionLabel(text="About"))
        about_label = Label(
            text=(
                "AetherionEXCAL Kivy Wallet\n"
                "Cross-platform mobile wallet for the EXCAL chain.\n\n"
                "Features:\n"
                "  - BIP-39 wallet with AES-256 encryption\n"
                "  - PKH, PQH, HTLC, QHTLC lock support\n"
                "  - Live chain dashboard\n"
                "  - Block explorer\n"
                "  - Transaction building and broadcasting\n\n"
                "Connects to node_rpc.py JSON-RPC server.\n"
                "Default port: 9432"
            ),
            color=COLORS["text_dim"],
            font_size="12sp",
        )
        content.add_widget(about_label)

        scroll.add_widget(content)
        layout.add_widget(scroll)
        self.add_widget(layout)

    def on_enter(self):
        app = ExcalWalletApp.instance()
        if app:
            self.rpc_url_input.text = app.rpc_url
            self.datadir_input.text = app.wallet_mgr.datadir

    def save_rpc_url(self, instance=None):
        app = ExcalWalletApp.instance()
        if app:
            new_url = self.rpc_url_input.text.strip()
            if new_url:
                app.set_rpc_url(new_url)


# ─── Navigation Drawer (Bottom Tab Bar) ────────────────────────────────

class TabBar(BoxLayout):
    """Bottom tab bar for navigation."""

    def __init__(self, screen_manager, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = 55
        self.spacing = 2
        self.canvas.before.do_color = lambda c: c.setter('rgba', COLORS["bg_panel"])

        self.sm = screen_manager
        self.tabs = [
            ("Dashboard", "dashboard", "📊"),
            ("Wallet", "wallet", "👛"),
            ("Send", "send", "📤"),
            ("Receive", "receive", "📥"),
            ("Explorer", "explorer", "🔍"),
            ("Locks", "locks", "🔐"),
            ("Settings", "settings", "⚙"),
        ]

        for label, name, icon in self.tabs:
            btn = Button(
                text=icon + "\n" + label,
                size_hint_x=1 / len(self.tabs),
                background_color=COLORS["bg_card"],
                color=COLORS["text_secondary"],
                font_size="10sp",
            )
            btn.bind(on_press=lambda instance, n=name: self.switch_screen(n))
            self.add_widget(btn)

    def switch_screen(self, name):
        self.sm.current = name


# ─── Main App ───────────────────────────────────────────────────────────

class ExcalWalletApp(App):
    """Main Kivy application."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rpc_url = "http://127.0.0.1:9432"
        self.rpc_client = None
        self.wallet_mgr = None
        self._instance = None

    @classmethod
    def instance(cls):
        """Get the running app instance."""
        return cls._instance

    def build(self):
        self._instance = self
        self.title = "AetherionEXCAL"
        Window.clearcolor = COLORS["bg_dark"]

        # Initialize components
        self.rpc_client = RpcClient(self.rpc_url)
        self.wallet_mgr = WalletManager()

        # Screen manager
        self.sm = ScreenManager()
        self.sm.add_widget(DashboardScreen(name="dashboard"))
        self.sm.add_widget(WalletScreen(name="wallet"))
        self.sm.add_widget(SendScreen(name="send"))
        self.sm.add_widget(ReceiveScreen(name="receive"))
        self.sm.add_widget(ExplorerScreen(name="explorer"))
        self.sm.add_widget(LocksScreen(name="locks"))
        self.sm.add_widget(SettingsScreen(name="settings"))

        # Main layout
        root = BoxLayout(orientation="vertical")
        root.add_widget(self.sm)
        root.add_widget(TabBar(self.sm))

        return root

    def set_rpc_url(self, url: str):
        """Update the RPC endpoint and reconnect."""
        self.rpc_url = url
        self.rpc_client = RpcClient(url)


if __name__ == "__main__":
    ExcalWalletApp().run()
