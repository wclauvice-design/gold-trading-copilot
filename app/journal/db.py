"""
Dispatcher : choisit automatiquement le backend du journal.
- Si DATABASE_URL / POSTGRES_URL est present dans l'environnement (cas de la
  prod sur Vercel, avec Vercel Postgres branche) -> postgres_store.
- Sinon (usage local) -> sqlite_store, fichier journal.db a la racine du projet.

Le reste de l'application (app/main.py) importe toujours simplement
`from app.journal import db as journal_db` et n'a pas a se soucier du backend.
"""
from app.config import settings

if settings.database_url:
    from app.journal import postgres_store as _backend
else:
    from app.journal import sqlite_store as _backend

init_db = _backend.init_db
create_trade = _backend.create_trade
update_execution = _backend.update_execution
close_trade = _backend.close_trade
delete_trade = _backend.delete_trade
list_trades = _backend.list_trades
get_trade = _backend.get_trade
get_stats = _backend.get_stats
