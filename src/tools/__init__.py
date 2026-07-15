from .diff import register as register_diff
from .fetch import register as register_fetch
from .scan import register as register_scan
from .search import register as register_search


def register_all(app):
    register_search(app)
    register_scan(app)
    register_fetch(app)
    register_diff(app)
