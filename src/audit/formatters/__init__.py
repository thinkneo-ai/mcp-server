from .json_fmt import format_json
from .cef import format_cef
from .leef import format_leef
from .syslog_fmt import format_syslog
from .csv_fmt import format_csv

FORMATTERS = {
    "json": format_json,
    "cef": format_cef,
    "leef": format_leef,
    "syslog": format_syslog,
    "csv": format_csv,
}
