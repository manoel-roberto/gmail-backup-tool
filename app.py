import sys
import os
import threading
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QFileDialog, 
    QProgressBar, QTextEdit, QMessageBox, QGroupBox,
    QDateEdit, QSpinBox, QCheckBox, QFormLayout, QComboBox,
    QListWidget, QListWidgetItem
)
from PyQt5.QtCore import pyqtSignal, QObject, Qt

from script import (
    fazer_backup_emails, 
    obter_servico_gmail, 
    consultar_primeiro_email, 
    consultar_email_mais_antigo,
    obter_info_conta_conectada,
    obter_marcadores_conta,
    desconectar_conta,
    DEFAULT_TOKEN_FILE
)

class WorkerSignals(QObject):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    account_signal = pyqtSignal(str, bool)
    labels_signal = pyqtSignal(list)

class EmailBackupApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Backup de E-mails do Gmail")
        self.resize(680, 680)
        self.signals = WorkerSignals()
        self.cancel_flag = False
        self._updating_list = False
        
        # Connect signals to GUI updates
        self.signals.log_signal.connect(self.log)
        self.signals.progress_signal.connect(self.update_progress)
        self.signals.finished_signal.connect(self.on_finished)
        self.signals.error_signal.connect(self.on_error)
        self.signals.account_signal.connect(self.set_account_status)
        self.signals.labels_signal.connect(self.update_labels_list)
        
        self.init_ui()
        self.refresh_account_status()

    def init_ui(self):
        main_layout = QVBoxLayout()
        
        # 1. Seção: Conta Google (Gmail)
        account_group = QGroupBox("Conta Google (Gmail)")
        account_layout = QVBoxLayout()
        
        self.account_status_label = QLabel("Verificando conta conectada...")
        self.account_status_label.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px;")
        account_layout.addWidget(self.account_status_label)
        
        account_btn_layout = QHBoxLayout()
        
        self.connect_btn = QPushButton("🔑 Conectar Conta")
        self.connect_btn.setToolTip("Conecta sua conta Google abrindo a tela de autorização no navegador.")
        self.connect_btn.clicked.connect(self.connect_account)
        account_btn_layout.addWidget(self.connect_btn)
        
        self.switch_btn = QPushButton("🔄 Trocar Conta")
        self.switch_btn.setToolTip("Abre o navegador para conectar uma nova conta Google ou trocar a conta atual.")
        self.switch_btn.clicked.connect(self.switch_account)
        account_btn_layout.addWidget(self.switch_btn)
        
        self.disconnect_btn = QPushButton("🚪 Desconectar Conta")
        self.disconnect_btn.setToolTip("Remove as credenciais da conta salva no aplicativo.")
        self.disconnect_btn.clicked.connect(self.disconnect_account)
        account_btn_layout.addWidget(self.disconnect_btn)
        
        account_layout.addLayout(account_btn_layout)
        account_group.setLayout(account_layout)
        main_layout.addWidget(account_group)
        
        # 2. Configurações
        config_group = QGroupBox("Configurações")
        config_layout = QVBoxLayout()
        
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("Pasta de Destino:"))
        self.out_input = QLineEdit()
        self.out_input.setText(os.path.join(os.getcwd(), "backup_emails"))
        out_layout.addWidget(self.out_input)
        
        out_btn = QPushButton("Procurar")
        out_btn.clicked.connect(self.browse_output)
        out_layout.addWidget(out_btn)
        config_layout.addLayout(out_layout)
        
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)
        
        # 3. Filtros e Opções
        filtros_group = QGroupBox("Filtros e Opções")
        filtros_layout = QFormLayout()
        
        # Seleção de Caixa / Marcador (Multi-seleção)
        marcador_container = QVBoxLayout()
        marcador_container.setSpacing(4)
        
        # Botões de atalho rápido
        btn_marcadores_layout = QHBoxLayout()
        btn_marcadores_layout.setSpacing(6)
        
        self.btn_sel_todas = QPushButton("🌐 Todas as Pastas")
        self.btn_sel_todas.setToolTip("Seleciona o backup completo de todas as pastas da conta.")
        self.btn_sel_todas.clicked.connect(self.selecionar_todas_pastas)
        btn_marcadores_layout.addWidget(self.btn_sel_todas)
        
        self.btn_sel_inbox_sent = QPushButton("📥 Inbox + 📤 Enviados")
        self.btn_sel_inbox_sent.setToolTip("Marca apenas Caixa de Entrada e Enviados.")
        self.btn_sel_inbox_sent.clicked.connect(self.selecionar_inbox_sent)
        btn_marcadores_layout.addWidget(self.btn_sel_inbox_sent)
        
        self.btn_limpar_sel = QPushButton("✕ Limpar")
        self.btn_limpar_sel.setToolTip("Desmarca todas as caixas.")
        self.btn_limpar_sel.clicked.connect(self.desmarcar_todas_pastas)
        btn_marcadores_layout.addWidget(self.btn_limpar_sel)
        
        marcador_container.addLayout(btn_marcadores_layout)
        
        # Lista de marcadores com checkboxes
        self.lista_marcadores = QListWidget()
        self.lista_marcadores.setMinimumHeight(110)
        self.lista_marcadores.setMaximumHeight(140)
        self.lista_marcadores.setStyleSheet("""
            QListWidget {
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                background-color: #ffffff;
                padding: 2px;
            }
            QListWidget::item {
                padding: 3px 5px;
                border-radius: 3px;
            }
            QListWidget::item:hover {
                background-color: #f0f4f8;
            }
            QListWidget::item:selected {
                background-color: #e3edf7;
                color: #000000;
            }
        """)
        self.lista_marcadores.itemChanged.connect(self.on_item_changed)
        self.lista_marcadores.itemDoubleClicked.connect(self.on_item_double_clicked)
        marcador_container.addWidget(self.lista_marcadores)
        
        # Resumo da seleção
        self.selection_summary_label = QLabel()
        self.selection_summary_label.setStyleSheet("font-size: 11px; padding: 2px;")
        marcador_container.addWidget(self.selection_summary_label)
        
        filtros_layout.addRow("Caixas / Marcadores:", marcador_container)
        
        self.organizar_check = QCheckBox("Criar subpastas para cada local/marcador (ex: Caixa de Entrada, Enviados, etc.)")
        self.organizar_check.setChecked(True)
        self.organizar_check.setToolTip("Cria pastas automaticamente no destino com o nome de cada caixa/marcador e organiza os e-mails dentro delas.")
        filtros_layout.addRow("", self.organizar_check)
        
        self.incluir_lixeira_spam_check = QCheckBox("Incluir Lixeira e Spam ao selecionar 'Todas as Caixas'")
        self.incluir_lixeira_spam_check.setChecked(False)
        filtros_layout.addRow("", self.incluir_lixeira_spam_check)
        
        self._popular_lista_padrao()
        
        self.enable_dates_check = QCheckBox("Filtrar por período de datas")
        self.enable_dates_check.toggled.connect(self.toggle_dates)
        filtros_layout.addRow(self.enable_dates_check)
        
        from PyQt5.QtCore import QDate
        hoje = QDate.currentDate()
        
        self.date_inicio = QDateEdit()
        self.date_inicio.setCalendarPopup(True)
        self.date_inicio.setDate(hoje.addMonths(-1))
        self.date_inicio.setEnabled(False)
        filtros_layout.addRow("Data Início (Depois de):", self.date_inicio)
        
        self.date_fim = QDateEdit()
        self.date_fim.setCalendarPopup(True)
        self.date_fim.setDate(hoje)
        self.date_fim.setEnabled(False)
        filtros_layout.addRow("Data Fim (Antes de):", self.date_fim)
        
        self.limite_spin = QSpinBox()
        self.limite_spin.setRange(0, 999999)
        self.limite_spin.setSpecialValueText("Sem limite")
        self.limite_spin.setValue(0)
        filtros_layout.addRow("Quantidade máxima:", self.limite_spin)
        
        self.apagar_check = QCheckBox("Apagar e-mails (Mover para lixeira) após o download automático")
        filtros_layout.addRow("", self.apagar_check)
        
        filtros_group.setLayout(filtros_layout)
        main_layout.addWidget(filtros_group)
        
        # 4. Botões de Ação
        consultas_layout = QHBoxLayout()
        self.query_first_btn = QPushButton("🔍 Consultar 1º E-mail (Mais Recente)")
        self.query_first_btn.clicked.connect(self.query_first_email)
        consultas_layout.addWidget(self.query_first_btn)
        
        self.query_oldest_btn = QPushButton("🕰️ Consultar E-mail Mais Antigo")
        self.query_oldest_btn.clicked.connect(self.query_oldest_email)
        consultas_layout.addWidget(self.query_oldest_btn)
        main_layout.addLayout(consultas_layout)
        
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("🚀 Iniciar Backup")
        self.start_btn.clicked.connect(self.start_backup_thread)
        btn_layout.addWidget(self.start_btn)
        
        self.cancel_btn = QPushButton("🛑 Cancelar")
        self.cancel_btn.clicked.connect(self.cancel_backup)
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.cancel_btn)
        
        main_layout.addLayout(btn_layout)
        
        # 5. Progresso
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        # 6. Log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #f4f4f4;")
        main_layout.addWidget(self.log_text)
        
        self.setLayout(main_layout)

    def _popular_lista_padrao(self):
        self._updating_list = True
        self.lista_marcadores.clear()
        
        item_todas = QListWidgetItem("🌐 Todas as Pastas da Conta (Backup Completo)")
        item_todas.setData(Qt.UserRole, "TODAS")
        item_todas.setFlags(item_todas.flags() | Qt.ItemIsUserCheckable)
        item_todas.setCheckState(Qt.Checked)
        self.lista_marcadores.addItem(item_todas)
        
        itens_padrao = [
            ('INBOX', '📥 Caixa de Entrada (INBOX)'),
            ('SENT', '📤 Enviados (SENT)'),
            ('DRAFT', '📝 Rascunhos (DRAFT)'),
            ('STARRED', '⭐ Com Estrela (STARRED)'),
            ('TRASH', '🗑️ Lixeira (TRASH)'),
            ('SPAM', '🚫 Spam (SPAM)')
        ]
        for lid, nome in itens_padrao:
            item = QListWidgetItem(nome)
            item.setData(Qt.UserRole, lid)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.lista_marcadores.addItem(item)
            
        self._updating_list = False
        self.update_selection_summary()

    def update_labels_list(self, labels):
        selecao_anterior = set(self.get_selected_labels())
        
        self._updating_list = True
        self.lista_marcadores.clear()
        
        item_todas = QListWidgetItem("🌐 Todas as Pastas da Conta (Backup Completo)")
        item_todas.setData(Qt.UserRole, "TODAS")
        item_todas.setFlags(item_todas.flags() | Qt.ItemIsUserCheckable)
        self.lista_marcadores.addItem(item_todas)
        
        nome_sistema = {
            'INBOX': '📥 Caixa de Entrada (INBOX)',
            'SENT': '📤 Enviados (SENT)',
            'DRAFT': '📝 Rascunhos (DRAFT)',
            'STARRED': '⭐ Com Estrela (STARRED)',
            'TRASH': '🗑️ Lixeira (TRASH)',
            'SPAM': '🚫 Spam (SPAM)'
        }
        for lid, nome_legivel in nome_sistema.items():
            if not labels or any(l.get('id') == lid for l in labels):
                item = QListWidgetItem(nome_legivel)
                item.setData(Qt.UserRole, lid)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                self.lista_marcadores.addItem(item)
                
        user_labels = [l for l in labels if l.get('type') == 'user']
        if user_labels:
            user_labels.sort(key=lambda x: x.get('name', '').lower())
            for l in user_labels:
                item = QListWidgetItem(f"📁 {l['name']}")
                item.setData(Qt.UserRole, l['id'])
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                self.lista_marcadores.addItem(item)
                
        restaurou_algum = False
        for i in range(self.lista_marcadores.count()):
            item = self.lista_marcadores.item(i)
            data = item.data(Qt.UserRole)
            if data in selecao_anterior:
                item.setCheckState(Qt.Checked)
                restaurou_algum = True
            else:
                item.setCheckState(Qt.Unchecked)
                
        if not restaurou_algum:
            item_todas.setCheckState(Qt.Checked)
            
        self._updating_list = False
        self.update_selection_summary()

    def on_item_changed(self, item):
        if self._updating_list:
            return
        self._updating_list = True
        try:
            data = item.data(Qt.UserRole)
            if data == 'TODAS' and item.checkState() == Qt.Checked:
                for i in range(self.lista_marcadores.count()):
                    other = self.lista_marcadores.item(i)
                    if other != item:
                        other.setCheckState(Qt.Unchecked)
            elif data != 'TODAS' and item.checkState() == Qt.Checked:
                for i in range(self.lista_marcadores.count()):
                    other = self.lista_marcadores.item(i)
                    if other.data(Qt.UserRole) == 'TODAS':
                        other.setCheckState(Qt.Unchecked)
        finally:
            self._updating_list = False
        self.update_selection_summary()

    def on_item_double_clicked(self, item):
        novo = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
        item.setCheckState(novo)

    def selecionar_todas_pastas(self):
        self._updating_list = True
        for i in range(self.lista_marcadores.count()):
            item = self.lista_marcadores.item(i)
            if item.data(Qt.UserRole) == 'TODAS':
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self._updating_list = False
        self.update_selection_summary()

    def selecionar_inbox_sent(self):
        self._updating_list = True
        for i in range(self.lista_marcadores.count()):
            item = self.lista_marcadores.item(i)
            data = item.data(Qt.UserRole)
            if data in ('INBOX', 'SENT'):
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self._updating_list = False
        self.update_selection_summary()

    def desmarcar_todas_pastas(self):
        self._updating_list = True
        for i in range(self.lista_marcadores.count()):
            item = self.lista_marcadores.item(i)
            item.setCheckState(Qt.Unchecked)
        self._updating_list = False
        self.update_selection_summary()

    def get_selected_labels(self):
        selected = []
        for i in range(self.lista_marcadores.count()):
            item = self.lista_marcadores.item(i)
            if item.checkState() == Qt.Checked:
                data = item.data(Qt.UserRole)
                if data:
                    selected.append(data)
        return selected

    def update_selection_summary(self):
        selected = self.get_selected_labels()
        if not selected:
            self.selection_summary_label.setText("⚠️ Nenhuma pasta selecionada (selecione ao menos uma)")
            self.selection_summary_label.setStyleSheet("color: #d9534f; font-weight: bold;")
            self.incluir_lixeira_spam_check.setEnabled(False)
        elif 'TODAS' in selected:
            self.selection_summary_label.setText("🌐 Backup Completo de Todas as Pastas da Conta")
            self.selection_summary_label.setStyleSheet("color: #0275d8; font-weight: bold;")
            self.incluir_lixeira_spam_check.setEnabled(True)
        else:
            nomes = []
            for i in range(self.lista_marcadores.count()):
                item = self.lista_marcadores.item(i)
                if item.checkState() == Qt.Checked:
                    texto_limpo = item.text()
                    for prefix in ['📥 ', '📤 ', '📝 ', '⭐ ', '🗑️ ', '🚫 ', '📁 ']:
                        texto_limpo = texto_limpo.replace(prefix, '')
                    nomes.append(texto_limpo.split('(')[0].strip())
            desc = ", ".join(nomes)
            if len(desc) > 65:
                desc = desc[:62] + "..."
            self.selection_summary_label.setText(f"✅ {len(nomes)} caixa(s) selecionada(s): {desc}")
            self.selection_summary_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            self.incluir_lixeira_spam_check.setEnabled(False)

    def set_account_status(self, text, is_connected):
        self.account_status_label.setText(text)
        self.connect_btn.setEnabled(not is_connected)
        self.switch_btn.setEnabled(is_connected)
        self.disconnect_btn.setEnabled(is_connected)

    def refresh_account_status(self):
        def check_task():
            info = obter_info_conta_conectada(DEFAULT_TOKEN_FILE)
            if info:
                self.signals.account_signal.emit(
                    f"🟢 Conectado como: {info['email']} ({info['messagesTotal']:,} e-mails na conta)",
                    True
                )
                labels = obter_marcadores_conta(DEFAULT_TOKEN_FILE)
                self.signals.labels_signal.emit(labels)
            else:
                self.signals.account_signal.emit(
                    "⚪ Nenhuma conta conectada (clique em 'Conectar Conta')",
                    False
                )
                self.signals.labels_signal.emit([])
        threading.Thread(target=check_task, daemon=True).start()

    def browse_output(self):
        directory = QFileDialog.getExistingDirectory(self, "Selecione a pasta de destino")
        if directory:
            self.out_input.setText(directory)

    def toggle_dates(self, checked):
        self.date_inicio.setEnabled(checked)
        self.date_fim.setEnabled(checked)

    def log(self, message):
        self.log_text.append(message)

    def update_progress(self, current, total):
        percentage = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(percentage)

    def on_finished(self):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.query_first_btn.setEnabled(True)
        self.query_oldest_btn.setEnabled(True)
        self.refresh_account_status()

    def on_error(self, message):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.query_first_btn.setEnabled(True)
        self.query_oldest_btn.setEnabled(True)
        self.refresh_account_status()
        QMessageBox.critical(self, "Erro", message)

    def cancel_backup(self):
        self.cancel_flag = True
        self.cancel_btn.setEnabled(False)
        self.log("Cancelamento solicitado, aguarde finalizar a etapa atual...")

    def connect_account(self):
        self._start_auth(forcar_login=False, title="Conectar Conta")

    def switch_account(self):
        self._start_auth(forcar_login=True, title="Trocar Conta")

    def _start_auth(self, forcar_login, title):
        self.connect_btn.setEnabled(False)
        self.switch_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self.log(f"[{title}] Abrindo navegador para autorização da conta Google...")
        
        def auth_task():
            try:
                service = obter_servico_gmail(
                    client_secrets_file=None,
                    token_file=DEFAULT_TOKEN_FILE,
                    forcar_login=forcar_login,
                    log_callback=lambda msg: self.signals.log_signal.emit(msg)
                )
                perfil = service.users().getProfile(userId='me').execute()
                email = perfil.get('emailAddress', 'Desconhecido')
                total = perfil.get('messagesTotal', 0)
                self.signals.account_signal.emit(
                    f"🟢 Conectado como: {email} ({total:,} e-mails na conta)",
                    True
                )
                self.signals.log_signal.emit(f"✅ Conta '{email}' conectada com sucesso!")
                labels = obter_marcadores_conta(DEFAULT_TOKEN_FILE)
                self.signals.labels_signal.emit(labels)
            except Exception as e:
                self.signals.log_signal.emit(f"❌ Erro na autorização: {e}")
                self.signals.error_signal.emit(str(e))
            finally:
                self.signals.finished_signal.emit()
                
        threading.Thread(target=auth_task, daemon=True).start()

    def disconnect_account(self):
        info = obter_info_conta_conectada(DEFAULT_TOKEN_FILE)
        msg = f"Deseja realmente desconectar da conta '{info['email']}'?" if info else "Deseja realmente desconectar a conta atual?"
        resposta = QMessageBox.question(self, "Desconectar Conta", msg, QMessageBox.Yes | QMessageBox.No)
        if resposta == QMessageBox.Yes:
            desconectar_conta(DEFAULT_TOKEN_FILE)
            self.set_account_status("⚪ Nenhuma conta conectada (clique em 'Conectar Conta')", False)
            self.signals.labels_signal.emit([])
            self.log("Conta desconectada com sucesso. Para nova consulta ou backup, conecte uma conta.")
            QMessageBox.information(self, "Desconectado", "Conta desconectada com sucesso.")

    def query_first_email(self):
        marcadores_sel = self.get_selected_labels()
        if not marcadores_sel:
            QMessageBox.warning(self, "Aviso", "Por favor, selecione ao menos uma caixa ou marcador para consultar.")
            return
        marcador_val = 'TODAS' if 'TODAS' in marcadores_sel else marcadores_sel

        self.query_first_btn.setEnabled(False)
        self.query_oldest_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.log_text.clear()
        
        def query_task():
            try:
                consultar_primeiro_email(
                    client_secrets_file=None,
                    token_file=DEFAULT_TOKEN_FILE,
                    log_callback=lambda msg: self.signals.log_signal.emit(msg),
                    marcador=marcador_val
                )
            except Exception as e:
                self.signals.error_signal.emit(str(e))
            finally:
                self.signals.finished_signal.emit()
                
        threading.Thread(target=query_task, daemon=True).start()

    def query_oldest_email(self):
        marcadores_sel = self.get_selected_labels()
        if not marcadores_sel:
            QMessageBox.warning(self, "Aviso", "Por favor, selecione ao menos uma caixa ou marcador para consultar.")
            return
        marcador_val = 'TODAS' if 'TODAS' in marcadores_sel else marcadores_sel

        self.query_oldest_btn.setEnabled(False)
        self.query_first_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.log_text.clear()
        
        def query_oldest_task():
            try:
                consultar_email_mais_antigo(
                    client_secrets_file=None,
                    token_file=DEFAULT_TOKEN_FILE,
                    log_callback=lambda msg: self.signals.log_signal.emit(msg),
                    marcador=marcador_val
                )
            except Exception as e:
                self.signals.error_signal.emit(str(e))
            finally:
                self.signals.finished_signal.emit()
                
        threading.Thread(target=query_oldest_task, daemon=True).start()

    def start_backup_thread(self):
        out_dir = self.out_input.text()
        marcadores_sel = self.get_selected_labels()
        if not marcadores_sel:
            QMessageBox.warning(self, "Aviso", "Por favor, selecione ao menos uma caixa ou marcador para realizar o backup.")
            return
        marcador_val = 'TODAS' if 'TODAS' in marcadores_sel else marcadores_sel
        organizar_val = self.organizar_check.isChecked()
        incluir_lixeira_spam_val = self.incluir_lixeira_spam_check.isChecked()

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.cancel_flag = False
        self.progress_bar.setValue(0)
        self.log_text.clear()
        
        if self.enable_dates_check.isChecked():
            dt_inicio = self.date_inicio.date().toString("yyyy/MM/dd")
            dt_fim = self.date_fim.date().toString("yyyy/MM/dd")
        else:
            dt_inicio = None
            dt_fim = None
        limite_val = self.limite_spin.value() if self.limite_spin.value() > 0 else None
        apagar_val = self.apagar_check.isChecked()
        
        if apagar_val:
            resposta = QMessageBox.warning(
                self, 
                "Aviso", 
                "Tem certeza de que deseja apagar os e-mails após o download? Esta ação moverá os e-mails para a lixeira.", 
                QMessageBox.Yes | QMessageBox.No
            )
            if resposta == QMessageBox.No:
                self.start_btn.setEnabled(True)
                self.cancel_btn.setEnabled(False)
                return
        
        def backup_task():
            self.signals.log_signal.emit("Iniciando processo de backup...")
            try:
                fazer_backup_emails(
                    pasta_destino=out_dir,
                    client_secrets_file=None,
                    token_file=DEFAULT_TOKEN_FILE,
                    log_callback=lambda msg: self.signals.log_signal.emit(msg),
                    progress_callback=lambda curr, tot: self.signals.progress_signal.emit(curr, tot),
                    check_cancel_callback=lambda: self.cancel_flag,
                    data_inicio=dt_inicio,
                    data_fim=dt_fim,
                    limite=limite_val,
                    apagar_apos_download=apagar_val,
                    marcador=marcador_val,
                    organizar_pastas=organizar_val,
                    incluir_lixeira_spam=incluir_lixeira_spam_val
                )
                self.signals.finished_signal.emit()
            except Exception as e:
                self.signals.error_signal.emit(str(e))
                
        threading.Thread(target=backup_task, daemon=True).start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EmailBackupApp()
    window.show()
    sys.exit(app.exec_())
