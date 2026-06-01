"""
Widgets de la UI (se construyen en la FASE 1 como réplica de ZaraRadio):

    onair_panel.py     -> "En el aire / Reproduciendo ahora": título, tiempo
                          restante (LCD), VU L/R, "Acaba a las".
    lcd_clock.py       -> reloj LCD con fecha + temperatura + humedad ("Siguiente").
    vu_widget.py       -> barras VU L/R verdes.
    file_tree.py       -> QTreeView explorador de carpetas (estilo Windows).
    playlist_view.py   -> tabla central (Título/Duración; rojo=sonando,
                          verde=siguiente; drag & drop; Duración Total).
    cartwall.py        -> 9 botones de cuñas (①..⑨).
    events_panel.py    -> "Eventos próximos" (Hora/Comienzo/Fichero/Duración).
    transport_bar.py   -> barra de transporte (play/stop/pausa/siguiente/cross) + slider.
    mentions_window.py -> ventana de menciones que BRILLA a la hora programada.
"""
