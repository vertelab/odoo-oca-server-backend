# Copyright 2018 Therp BV <https://therp.nl>
# Copyright 2019-2020 initOS GmbH <https://initos.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import base64
import os
import time
from contextlib import contextmanager
from colorsys import hsv_to_rgb
from os.path import basename, dirname, expanduser, join
from time import gmtime, strftime
from typing import (Iterable, Iterator, Mapping, Optional, Tuple, Union,
                    overload)
from radicale import types
from radicale.item import Item
from radicale.log import logger
from radicale.pathutils import sanitize_path

from odoo.http import request

from radicale.storage import BaseCollection, BaseStorage

try:
    from radicale.storage import Item, get_etag
except ImportError:
    BaseCollection = None
    Item = None
    get_etag = None


class BytesPretendingToBeString(bytes):
    # radicale expects a string as file content, so we provide the str
    # functions needed
    def encode(self, encoding):
        return self


class FileItem:

    def __init__(self, item):
        self.item = item


    """this item tricks radicalev into serving a plain file"""
    @property
    def name(self):
        return 'VCARD'

    def serialize(self):
        return BytesPretendingToBeString(base64.b64decode(self.item.datas))

    @property
    def etag(self):
        return get_etag(self.item.datas.decode('ascii'))


class Collection:
    @classmethod
    def static_init(cls):
        pass

    @classmethod
    def _split_path(cls, path):
        return list(filter(
            None, os.path.normpath(path or '').strip('/').split('/')
        ))

    @classmethod
    def discover(cls, path, depth=None):
        depth = int(depth or "0")
        components = cls._split_path(path)
        collection = cls(path)
        if len(components) > 2:
            # TODO: this probably better should happen in some dav.collection
            # function
            if collection.collection.dav_type == 'files' and depth:
                for href in collection.list():
                    yield collection.get(href)
                    return
            yield collection.get(path)
            return
        yield collection
        if depth and len(components) == 1:
            for collection in request.env['dav.collection'].search([]):
                yield cls('/'.join(components + ['/%d' % collection.id]))
        if depth and len(components) == 2:
            for href in collection.list():
                yield collection.get(href)

    @classmethod
    @contextmanager
    def acquire_lock(cls, mode, user=None):
        """We have a database for that"""
        yield

    @property
    def env(self):
        return request.env

    @property
    def last_modified(self):
        return self._odoo_to_http_datetime(self.collection.create_date)

    def __init__(self, path):
        self.path_components = self._split_path(path)
        self.path = '/'.join(self.path_components) or '/'
        self.collection = self.env['dav.collection']
        if len(self.path_components) >= 2 and str(
                self.path_components[1]
        ).isdigit():
            self.collection = self.env['dav.collection'].browse(int(
                self.path_components[1]
            ))

    def _odoo_to_http_datetime(self, value):
        return time.strftime(
            '%a, %d %b %Y %H:%M:%S GMT',
            time.strptime(value, '%Y-%m-%d %H:%M:%S'),
        )

    def get_meta(self, key=None):
        if key is None:
            return {}
        elif key == 'tag':
            return self.collection.tag
        elif key == 'D:displayname':
            return self.collection.display_name
        elif key == 'C:supported-calendar-component-set':
            return 'VTODO,VEVENT,VJOURNAL'
        elif key == 'C:calendar-home-set':
            return None
        elif key == 'D:principal-URL':
            return None
        elif key == 'ICAL:calendar-color':
            # TODO: set in dav.collection
            return '#48c9f4'
        self.logger.warning('unsupported metadata %s', key)

    def get(self, href):
        return self.collection.dav_get(self, href)

    def upload(self, href, vobject_item):
        return self.collection.dav_upload(self, href, vobject_item)

    def delete(self, href):
        return self.collection.dav_delete(self, self._split_path(href))

    def list(self):
        return self.collection.dav_list(self, self.path_components)


class Storage(BaseStorage):
    def __init__(self, configuration: "config.Configuration") -> None:
        """Initialize BaseStorage.
        ``configuration`` see ``radicale.config`` module.
        The ``configuration`` must not change during the lifetime of
        this object, it is kept as an internal reference.
        """
        super().__init__(configuration)
        self.adapters: list[Union[Abook, IcsTask, Remind]] = []
        self.filesystem_folder = expanduser(
            configuration.get("storage", "filesystem_folder")
        )

        if "remind_file" in configuration.options("storage"):
            zone = None
            if "remind_timezone" in configuration.options("storage"):
                zone = ZoneInfo(configuration.get("storage", "remind_timezone"))
            month = 15
            if "remind_lookahead_month" in configuration.options("storage"):
                month = configuration.get("storage", "remind_lookahead_month")
            self.adapters.append(
                Remind(configuration.get("storage", "remind_file"), zone, month=month)
            )

        if "abook_file" in configuration.options("storage"):
            self.adapters.append(Abook(configuration.get("storage", "abook_file")))

        if "task_folder" in configuration.options("storage"):
            task_folder = configuration.get("storage", "task_folder")
            task_projects = []
            if "task_projects" in configuration.options("storage"):
                task_projects = configuration.get("storage", "task_projects").split(",")
            task_start = True
            if "task_start" in configuration.options("storage"):
                task_start = configuration.get("storage", "task_start")
            self.adapters.append(
                IcsTask(task_folder, task_projects=task_projects, start_task=task_start)
            )

    # fmt: off
    def discover(self, path: str, depth: str = "0") -> Iterable[
        "types.CollectionOrItem"]:
        """Discover a list of collections under the given ``path``.
        ``path`` is sanitized.
        If ``depth`` is "0", only the actual object under ``path`` is
        returned.
        If ``depth`` is anything but "0", it is considered as "1" and direct
        children are included in the result.
        The root collection "/" must always exist.
        """
        # fmt: on
        if path.count("/") < 3:
            # yield MinCollection(path)

            if depth != "0":
                for adapter in self.adapters:
                    for filename in adapter.get_filesnames():
                        yield Collection(
                            filename.replace(self.filesystem_folder, ""),
                            filename,
                            adapter,
                        )
            return

        filename = join(self.filesystem_folder, dirname(path).strip("/"))
        collection = None

        for adapter in self.adapters:
            if filename in adapter.get_filesnames():
                collection = Collection(path, filename, adapter)
                break

        if not collection:
            return

        if path.endswith("/"):
            yield collection

            if depth != "0":
                for uid in collection._list():
                    yield collection._get(uid)
            return

        if basename(path) in collection._list():
            yield collection._get(basename(path))
            return

    # fmt: off
    def move(self, item: "radicale_item.Item", to_collection: BaseCollection,
             to_href: str) -> None:
        """Move an object.
        ``item`` is the item to move.
        ``to_collection`` is the target collection.
        ``to_href`` is the target name in ``to_collection``. An item with the
        same name might already exist.
        """
        # fmt: on
        if not isinstance(item.collection, Collection) or not isinstance(to_collection, Collection):
            pass

        if item.collection.path == to_collection.path and item.href == to_href:
            return

        to_collection.adapter.move_vobject(
            to_href, item.collection.filename, to_collection.filename
        )

    @types.contextmanager
    def acquire_lock(self, mode: str, user: str = "") -> Iterator[None]:
        """Set a context manager to lock the whole storage.
        ``mode`` must either be "r" for shared access or "w" for exclusive
        access.
        ``user`` is the name of the logged in user or empty.
        """
        yield

    def verify(self) -> bool:
        """Check the storage for errors."""
        return True

    def create_collection(
            self, href: str,
            items: Optional[Iterable["radicale_item.Item"]] = None,
            props: Optional[Mapping[str, str]] = None) -> BaseCollection:
        yield
