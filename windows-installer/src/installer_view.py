from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence, QResizeEvent
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class InstallerViewMixin:
    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("rootWidget")
        central.setAccessibleName("Основная область установщика")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("heroFrame")
        hero.setAccessibleName("Сведения о программе")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(20, 16, 20, 16)
        hero_layout.setSpacing(4)
        eyebrow = QLabel("BRAILLE EMOTION · WINDOWS")
        eyebrow.setObjectName("eyebrowLabel")
        eyebrow.setAccessibleName("Braille eMotion. Программа для Windows")
        hero_layout.addWidget(eyebrow)

        heading = QLabel("Диспетчер приложений")
        heading.setObjectName("headingLabel")
        heading.setWordWrap(True)
        heading_font = QFont(heading.font())
        heading_font.setPointSize(max(18, heading_font.pointSize() + 6))
        heading_font.setBold(True)
        heading.setFont(heading_font)
        heading.setAccessibleName("Заголовок. Установщик Диспетчера приложений для Braille eMotion")
        hero_layout.addWidget(heading)

        subtitle = QLabel(
            "Установка, восстановление и удаление Диспетчера приложений на подключённом Braille eMotion."
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        subtitle.setAccessibleName("Назначение программы")
        hero_layout.addWidget(subtitle)
        outer.addWidget(hero)

        self.status_frame = QFrame()
        self.status_frame.setObjectName("statusFrame")
        self.status_frame.setProperty("statusLevel", "status")
        self.status_frame.setAccessibleName("Текущее состояние программы")
        status_layout = QVBoxLayout(self.status_frame)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(6)

        self.status_badge = QLabel("СОСТОЯНИЕ")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAccessibleName("Тип сообщения. Состояние")
        status_layout.addWidget(self.status_badge)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setFocusPolicy(Qt.StrongFocus)
        self.status_label.setProperty("focusableStatus", True)
        self.status_label.setMinimumHeight(44)
        self.status_label.setAccessibleName("Текущее состояние")
        self.status_label.setAccessibleDescription(
            "Текстовое описание подключения или выполняемой операции. Нажмите F6, чтобы перейти сюда."
        )
        status_layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Ожидание — %p%")
        self.progress.setTextVisible(True)
        self.progress.setAccessibleName("Ход операции")
        self.progress.setAccessibleDescription(
            "Процент выполнения установки или удаления. Состояние также сообщается текстом выше."
        )
        status_layout.addWidget(self.progress)
        outer.addWidget(self.status_frame)

        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Разделы установщика")
        self.tabs.setAccessibleDescription(
            "Три раздела: главная страница, журнал и справка. Ctrl+1, Ctrl+2 и Ctrl+3 переключают разделы."
        )
        self.tabs.tabBar().setAccessibleName("Вкладки разделов установщика")
        self.tabs.setFocusPolicy(Qt.StrongFocus)
        self.tabs.setDocumentMode(False)
        outer.addWidget(self.tabs, 1)

        self.main_tab = QWidget()
        self.log_tab = QWidget()
        self.help_tab = QWidget()
        self.tabs.addTab(self.main_tab, "&Главная")
        self.tabs.addTab(self.log_tab, "&Журнал")
        self.tabs.addTab(self.help_tab, "&Справка")

        self._build_main_tab()
        self._build_log_tab()
        self._build_help_tab()

        self.setCentralWidget(central)
        self.main_focus_order = (
            self.device_combo,
            self.refresh_button,
            self.device_details,
            self.app_status_label,
            self.install_button,
            self.uninstall_button,
            self.open_help_button,
            self.open_log_button,
            self.close_button,
        )
        self._apply_responsive_layout(self.width())

    def _configure_tab_order(self) -> None:
        """Restore the semantic order after widgets move between layouts."""
        self.setTabOrder(self.status_label, self.tabs)
        self.setTabOrder(self.tabs, self.device_combo)
        self.setTabOrder(self.device_combo, self.refresh_button)
        self.setTabOrder(self.refresh_button, self.device_details)
        self.setTabOrder(self.device_details, self.app_status_label)
        self.setTabOrder(self.app_status_label, self.install_button)
        self.setTabOrder(self.install_button, self.uninstall_button)
        self.setTabOrder(self.uninstall_button, self.open_help_button)
        self.setTabOrder(self.open_help_button, self.open_log_button)
        self.setTabOrder(self.open_log_button, self.close_button)
        self.setTabOrder(self.copy_log_button, self.save_log_button)
        self.setTabOrder(self.save_log_button, self.clear_log_button)
        self.setTabOrder(self.help_topics, self.help_paragraphs)

    def _build_main_tab(self) -> None:
        tab_layout = QVBoxLayout(self.main_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.main_scroll.setAccessibleName("Прокручиваемая главная страница")
        self.main_scroll.setAccessibleDescription(
            "Если окно маленькое или текст увеличен, используйте Page Up и Page Down для прокрутки."
        )
        tab_layout.addWidget(self.main_scroll)

        self.main_content = QWidget()
        self.main_content.setMaximumWidth(1080)
        self.main_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.main_layout = QGridLayout(self.main_content)
        self.main_layout.setContentsMargins(12, 14, 12, 16)
        self.main_layout.setHorizontalSpacing(14)
        self.main_layout.setVerticalSpacing(14)
        self.main_scroll.setWidget(self.main_content)

        self.device_group = QGroupBox("Подключённое устройство")
        self.device_group.setAccessibleName("Подключённое устройство")
        self.device_layout = QGridLayout(self.device_group)
        self.device_layout.setContentsMargins(16, 18, 16, 16)
        self.device_layout.setHorizontalSpacing(10)
        self.device_layout.setVerticalSpacing(10)

        self.device_label = QLabel("Braille eMotion:")
        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(44)
        self.device_combo.setAccessibleName("Список найденных устройств")
        self.device_combo.setAccessibleDescription(
            "Выберите серийный номер Braille eMotion. Несовместимые устройства нельзя изменить."
        )
        self.device_combo.currentIndexChanged.connect(self._selected_device_changed)
        self.device_label.setBuddy(self.device_combo)

        self.refresh_button = QPushButton("&Обновить список устройств")
        self.refresh_button.setMinimumHeight(48)
        self.refresh_button.setAccessibleName("Обновить список устройств")
        self.refresh_button.setAccessibleDescription(
            "Повторно запускает автоматический поиск через встроенный ADB. Ctrl+R или Alt+О."
        )
        self.refresh_button.clicked.connect(self.request_scan)

        self.device_details = QPlainTextEdit()
        self.device_details.setReadOnly(True)
        self.device_details.setMinimumHeight(100)
        self.device_details.setMaximumHeight(132)
        self.device_details.setAccessibleName("Сведения о выбранном устройстве")
        self.device_details.setAccessibleDescription(
            "Модель, версия Android и результат проверки совместимости Braille eMotion."
        )
        self.device_details.setPlainText("Устройства ещё не найдены.")

        self.app_status_group = QGroupBox("Состояние Диспетчера приложений")
        self.app_status_group.setAccessibleName(
            "Состояние Диспетчера приложений на устройстве"
        )
        status_layout = QVBoxLayout(self.app_status_group)
        status_layout.setContentsMargins(16, 18, 16, 16)
        self.app_status_label = QPlainTextEdit("Состояние ещё не проверено.")
        self.app_status_label.setObjectName("appStatusLabel")
        self.app_status_label.setProperty("appState", "neutral")
        self.app_status_label.setReadOnly(True)
        self.app_status_label.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.app_status_label.setTabChangesFocus(True)
        self.app_status_label.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.app_status_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.app_status_label.setFocusPolicy(Qt.StrongFocus)
        self.app_status_label.setProperty("focusableStatus", True)
        self.app_status_label.setMinimumHeight(74)
        self.app_status_label.setMaximumHeight(100)
        self.app_status_label.setAccessibleName("Статус установленного Диспетчера приложений")
        self.app_status_label.setAccessibleDescription(
            "Сообщает, установлен ли диспетчер полностью, отсутствует или установлен не полностью."
        )
        status_layout.addWidget(self.app_status_label)
        self.actions_group = QGroupBox("Действия")
        self.actions_group.setAccessibleName("Действия с Диспетчером приложений")
        self.actions_layout = QGridLayout(self.actions_group)
        self.actions_layout.setContentsMargins(16, 18, 16, 16)
        self.actions_layout.setHorizontalSpacing(10)
        self.actions_layout.setVerticalSpacing(10)

        self.install_button = QPushButton("&Установить Диспетчер приложений")
        self.install_button.setMinimumHeight(52)
        self.install_button.setProperty("primaryAction", True)
        self.install_button.setEnabled(False)
        self.install_button.setAccessibleName("Установить Диспетчер приложений")
        self.install_button.setAccessibleDescription(
            "Устанавливает версию 1.5 и пункт заводского меню. Перед началом требуется подтверждение. Alt+У."
        )
        self.install_button.clicked.connect(self.confirm_install)

        self.uninstall_button = QPushButton("У&далить Диспетчер приложений")
        self.uninstall_button.setMinimumHeight(52)
        self.uninstall_button.setProperty("dangerAction", True)
        self.uninstall_button.setEnabled(False)
        self.uninstall_button.setAccessibleName("Удалить Диспетчер приложений")
        self.uninstall_button.setAccessibleDescription(
            "Удаляет только Диспетчер приложений, его мост и старую версию диспетчера. Alt+Д."
        )
        self.uninstall_button.clicked.connect(self.confirm_uninstall)

        self.open_help_button = QPushButton("&Справка и ответственность")
        self.open_help_button.setMinimumHeight(48)
        self.open_help_button.setAccessibleName("Открыть справку и ответственность")
        self.open_help_button.setAccessibleDescription(
            "Открывает справку. Первая тема содержит ответственность и предупреждение о гарантии. F1."
        )
        self.open_help_button.clicked.connect(self.focus_help)

        self.open_log_button = QPushButton("&Журнал")
        self.open_log_button.setMinimumHeight(48)
        self.open_log_button.setAccessibleName("Открыть журнал")
        self.open_log_button.setAccessibleDescription(
            "Открывает журнал команд и результатов. Ctrl+L."
        )
        self.open_log_button.clicked.connect(self.focus_log)

        self.close_button = QPushButton("&Закрыть установщик")
        self.close_button.setMinimumHeight(48)
        self.close_button.setAccessibleName("Закрыть установщик")
        self.close_button.setAccessibleDescription(
            "Закрывает программу. Во время установки или удаления закрытие заблокировано."
        )
        self.close_button.clicked.connect(self.close)

    def _build_log_tab(self) -> None:
        layout = QVBoxLayout(self.log_tab)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(10)

        description = QLabel(
            "Журнал обновляется во время работы. Здесь есть технические команды, серийный номер и результаты проверок."
        )
        description.setObjectName("sectionDescription")
        description.setWordWrap(True)
        description.setAccessibleName("Описание журнала")
        layout.addWidget(description)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_view.setAccessibleName("Журнал работы")
        self.log_view.setAccessibleDescription(
            "Доступный только для чтения журнал. Ctrl+A выделяет всё, Ctrl+C копирует."
        )
        layout.addWidget(self.log_view, 1)

        self.log_actions_layout = QGridLayout()
        self.log_actions_layout.setHorizontalSpacing(10)
        self.log_actions_layout.setVerticalSpacing(10)
        self.copy_log_button = QPushButton("Копировать журнал")
        self.copy_log_button.setMinimumHeight(48)
        self.copy_log_button.setAccessibleName("Копировать весь журнал")
        self.copy_log_button.clicked.connect(self.copy_log)
        self.save_log_button = QPushButton("Сохранить журнал…")
        self.save_log_button.setMinimumHeight(48)
        self.save_log_button.setAccessibleName("Сохранить журнал в текстовый файл")
        self.save_log_button.clicked.connect(self.save_log)
        self.clear_log_button = QPushButton("Очистить журнал")
        self.clear_log_button.setMinimumHeight(48)
        self.clear_log_button.setAccessibleName("Очистить журнал на экране")
        self.clear_log_button.clicked.connect(self.clear_log)
        layout.addLayout(self.log_actions_layout)

    def _build_help_tab(self) -> None:
        layout = QVBoxLayout(self.help_tab)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(10)

        intro = QLabel(
            "Сначала выберите тему стрелками. Затем нажмите Tab и читайте абзацы по одному стрелками. Ответственность и гарантия находятся в первой теме."
        )
        intro.setObjectName("sectionDescription")
        intro.setWordWrap(True)
        intro.setAccessibleName("Как читать справку")
        layout.addWidget(intro)

        self.help_splitter = QSplitter(Qt.Horizontal)
        self.help_splitter.setChildrenCollapsible(False)
        self.help_splitter.setAccessibleName("Темы и абзацы справки")
        self.help_splitter.setAccessibleDescription(
            "На широком окне темы находятся слева, абзацы справа; на узком — темы сверху, абзацы снизу."
        )

        topic_panel = QGroupBox("Темы справки")
        topic_column = QVBoxLayout(topic_panel)
        topic_column.setContentsMargins(12, 18, 12, 12)
        paragraph_panel = QGroupBox("Содержание выбранной темы")
        paragraph_column = QVBoxLayout(paragraph_panel)
        paragraph_column.setContentsMargins(12, 18, 12, 12)

        topic_label = QLabel("Темы справки:")
        self.help_topics = QListWidget()
        self.help_topics.setMinimumHeight(150)
        self.help_topics.setAccessibleName("Темы справки")
        self.help_topics.setAccessibleDescription(
            "Ответственность и гарантия — первая тема. Используйте стрелки и затем Tab."
        )
        topic_label.setBuddy(self.help_topics)
        self.help_topics.currentRowChanged.connect(self._help_topic_changed)
        topic_column.addWidget(topic_label)
        topic_column.addWidget(self.help_topics, 1)

        self.paragraph_label = QLabel("Абзацы выбранной темы:")
        self.help_paragraphs = QListWidget()
        self.help_paragraphs.setMinimumHeight(190)
        self.help_paragraphs.setWordWrap(True)
        self.help_paragraphs.setUniformItemSizes(False)
        self.help_paragraphs.setAccessibleName("Абзацы справки")
        self.help_paragraphs.setAccessibleDescription(
            "Каждый элемент — отдельный абзац. Используйте стрелки, чтобы читать по одному."
        )
        self.paragraph_label.setBuddy(self.help_paragraphs)
        paragraph_column.addWidget(self.paragraph_label)
        paragraph_column.addWidget(self.help_paragraphs, 1)

        self.help_splitter.addWidget(topic_panel)
        self.help_splitter.addWidget(paragraph_panel)
        self.help_splitter.setStretchFactor(0, 2)
        self.help_splitter.setStretchFactor(1, 5)
        self.help_splitter.setSizes([280, 700])
        layout.addWidget(self.help_splitter, 1)

    def _apply_responsive_layout(self, available_width: int) -> None:
        compact = available_width < 760
        if self._compact_layout == compact:
            return
        focused = QApplication.focusWidget()
        self._compact_layout = compact

        for group in (self.device_group, self.app_status_group, self.actions_group):
            self.main_layout.removeWidget(group)
        if compact:
            self.main_layout.addWidget(self.device_group, 0, 0)
            self.main_layout.addWidget(self.app_status_group, 1, 0)
            self.main_layout.addWidget(self.actions_group, 2, 0)
            self.main_layout.setColumnStretch(0, 1)
            self.main_layout.setColumnStretch(1, 0)
            self.main_layout.setRowStretch(2, 0)
            self.main_layout.setRowStretch(3, 1)
        else:
            self.main_layout.addWidget(self.device_group, 0, 0, 1, 2)
            self.main_layout.addWidget(self.app_status_group, 1, 0)
            self.main_layout.addWidget(self.actions_group, 1, 1)
            self.main_layout.setColumnStretch(0, 1)
            self.main_layout.setColumnStretch(1, 1)
            self.main_layout.setRowStretch(2, 1)
            self.main_layout.setRowStretch(3, 0)

        for widget in (
            self.device_label,
            self.device_combo,
            self.refresh_button,
            self.device_details,
        ):
            self.device_layout.removeWidget(widget)
        if compact:
            self.device_layout.addWidget(self.device_label, 0, 0)
            self.device_layout.addWidget(self.device_combo, 1, 0)
            self.device_layout.addWidget(self.refresh_button, 2, 0)
            self.device_layout.addWidget(self.device_details, 3, 0)
            self.device_layout.setColumnStretch(0, 1)
            self.device_layout.setColumnStretch(1, 0)
            self.device_layout.setColumnStretch(2, 0)
        else:
            self.device_layout.addWidget(self.device_label, 0, 0)
            self.device_layout.addWidget(self.device_combo, 0, 1)
            self.device_layout.addWidget(self.refresh_button, 0, 2)
            self.device_layout.addWidget(self.device_details, 1, 0, 1, 3)
            self.device_layout.setColumnStretch(0, 0)
            self.device_layout.setColumnStretch(1, 1)
            self.device_layout.setColumnStretch(2, 0)

        action_widgets = (
            self.install_button,
            self.uninstall_button,
            self.open_help_button,
            self.open_log_button,
            self.close_button,
        )
        for widget in action_widgets:
            self.actions_layout.removeWidget(widget)
        if compact:
            for row, widget in enumerate(action_widgets):
                self.actions_layout.addWidget(widget, row, 0)
            self.actions_layout.setColumnStretch(0, 1)
            self.actions_layout.setColumnStretch(1, 0)
        else:
            self.actions_layout.addWidget(self.install_button, 0, 0)
            self.actions_layout.addWidget(self.uninstall_button, 0, 1)
            self.actions_layout.addWidget(self.open_help_button, 1, 0)
            self.actions_layout.addWidget(self.open_log_button, 1, 1)
            self.actions_layout.addWidget(self.close_button, 2, 0, 1, 2)
            self.actions_layout.setColumnStretch(0, 1)
            self.actions_layout.setColumnStretch(1, 1)

        log_widgets = (
            self.copy_log_button,
            self.save_log_button,
            self.clear_log_button,
        )
        for widget in log_widgets:
            self.log_actions_layout.removeWidget(widget)
        if compact:
            for row, widget in enumerate(log_widgets):
                self.log_actions_layout.addWidget(widget, row, 0)
            self.log_actions_layout.setColumnStretch(0, 1)
            self.log_actions_layout.setColumnStretch(1, 0)
            self.log_actions_layout.setColumnStretch(2, 0)
            self.help_splitter.setOrientation(Qt.Vertical)
            self.help_splitter.setSizes([220, 360])
        else:
            for column, widget in enumerate(log_widgets):
                self.log_actions_layout.addWidget(widget, 0, column)
                self.log_actions_layout.setColumnStretch(column, 1)
            self.help_splitter.setOrientation(Qt.Horizontal)
            self.help_splitter.setSizes([280, 700])

        arrangement = "компактное, элементы расположены сверху вниз" if compact else (
            "широкое, связанные элементы расположены в две колонки"
        )
        self._refresh_responsive_labels()
        self.main_scroll.setAccessibleDescription(
            f"Текущее расположение: {arrangement}. При необходимости используйте Page Up и Page Down."
        )
        self._configure_tab_order()
        if focused and QApplication.focusWidget() is None and focused.isVisible():
            QTimer.singleShot(0, focused.setFocus)

    def _refresh_responsive_labels(self) -> None:
        compact = bool(self._compact_layout)
        install_name = self.install_button.accessibleName()
        compact_install = {
            "Установить Диспетчер приложений": "&Установить",
            "Восстановить Диспетчер приложений": "&Восстановить",
            "Переустановить Диспетчер приложений": "Пере&установить",
        }.get(install_name, "&Установить")
        wide_install = {
            "Установить Диспетчер приложений": "&Установить Диспетчер приложений",
            "Восстановить Диспетчер приложений": "&Восстановить Диспетчер приложений",
            "Переустановить Диспетчер приложений": "Пере&установить Диспетчер приложений",
        }.get(install_name, "&Установить Диспетчер приложений")
        self.install_button.setText(compact_install if compact else wide_install)
        self.uninstall_button.setText("У&далить" if compact else "У&далить Диспетчер приложений")
        self.open_help_button.setText("&Справка" if compact else "&Справка и ответственность")
        self.open_log_button.setText("&Журнал")
        self.close_button.setText("&Закрыть" if compact else "&Закрыть установщик")
        self.app_status_group.setTitle(
            "Состояние" if compact else "Состояние Диспетчера приложений"
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("F1"), self, activated=self.focus_help)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.focus_log)
        QShortcut(QKeySequence("F6"), self, activated=self.status_label.setFocus)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.request_scan)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=self.focus_main)
        QShortcut(QKeySequence("Ctrl+2"), self, activated=self.focus_log)
        QShortcut(QKeySequence("Ctrl+3"), self, activated=self.focus_help)
        QShortcut(QKeySequence("Escape"), self, activated=self._escape_pressed)
        QShortcut(QKeySequence("Alt+У"), self, activated=self.confirm_install)
        QShortcut(QKeySequence("Alt+Д"), self, activated=self.confirm_uninstall)
        QShortcut(QKeySequence("Alt+О"), self, activated=self.request_scan)
        QShortcut(QKeySequence("Alt+С"), self, activated=self.focus_help)
        QShortcut(QKeySequence("Alt+Ж"), self, activated=self.focus_log)
        QShortcut(QKeySequence("Alt+З"), self, activated=self.close)
