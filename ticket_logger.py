"""
Модуль для логирования всех изменений заявок в таблицу ticket_history.
"""

def log_ticket_change(conn, ticket_id, change_type, changed_by,
                      field_name=None, old_value=None, new_value=None,
                      description=None):
    """
    Логирует изменение заявки в ticket_history.

    Args:
        conn: Соединение с БД
        ticket_id: ID заявки
        change_type: Тип изменения (ticket_created, status_change, assignment, unassignment, etc.)
        changed_by: ID пользователя, который сделал изменение
        field_name: Имя измененного поля (опционально)
        old_value: Старое значение (опционально)
        new_value: Новое значение (опционально)
        description: Описание изменения (опционально)
    """
    conn.execute("""
        INSERT INTO ticket_history
        (ticket_id, changed_by, change_type, field_name, old_value, new_value, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (ticket_id, changed_by, change_type, field_name, old_value, new_value, description))
    conn.commit()
