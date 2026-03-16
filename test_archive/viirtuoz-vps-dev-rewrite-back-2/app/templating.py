"""Jinja2Templates subclass that emits path-only URLs.

Starlette's default ``url_for`` generates absolute URLs
(``https://host/static/css/…``).  Behind a Kubernetes ingress the
scheme/host derived from proxy headers is often wrong, causing the
browser to request CSS/JS from an unreachable internal address.

This subclass overrides ``url_for`` to return only the path component
(``/static/css/…``), which always resolves relative to the current
origin regardless of reverse-proxy configuration.
"""

from jinja2 import pass_context
from starlette.templating import Jinja2Templates as _Base


class Jinja2Templates(_Base):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        @pass_context
        def url_for(context: dict, name: str, /, **path_params) -> str:
            request = context["request"]
            return request.url_for(name, **path_params).path

        self.env.globals["url_for"] = url_for
