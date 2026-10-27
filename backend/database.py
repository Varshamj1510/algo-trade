from sqlalchemy import inspect
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()
        strategy_columns = {
            column['name'] for column in inspect(db.engine).get_columns('strategies')
        }
        migrations = {
            'buy_logic': 'VARCHAR(3)',
            'buy_conditions': 'TEXT',
            'sell_logic': 'VARCHAR(3)',
            'sell_conditions': 'TEXT',
        }
        missing_columns = {
            name: definition
            for name, definition in migrations.items()
            if name not in strategy_columns
        }
        if missing_columns:
            with db.engine.begin() as connection:
                for name, definition in missing_columns.items():
                    connection.exec_driver_sql(
                        f'ALTER TABLE strategies ADD COLUMN {name} {definition}'
                    )
        alert_settings_columns = {
            column['name']
            for column in inspect(db.engine).get_columns('alert_notification_settings')
        }
        if 'timezone' not in alert_settings_columns:
            with db.engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE alert_notification_settings ADD COLUMN timezone "
                    "VARCHAR(64) NOT NULL DEFAULT 'UTC'"
                )
