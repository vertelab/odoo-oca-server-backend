# Copyright 2018 Therp BV <https://therp.nl>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from .collection import Collection

try:
    from radicale.rights import authenticated
except ImportError:
    AuthenticatedRights = OwnerOnlyRights = OwnerWriteRights = None


class Rights(authenticated.Rights):
    # def __init__(self, OwnerOnlyRights, OwnerWriteRights, AuthenticatedRights):
    #     self.OwnerOnlyRights = OwnerOnlyRights
    #     self.OwnerWriteRights = OwnerWriteRights
    #     self.AuthenticatedRights = AuthenticatedRights

    def authorized(self, user, path, perm):
        if path == '/':
            return True

        collection = Collection(path)
        if not collection.collection:
            return False

        rights = collection.collection.sudo().rights
        cls = {
            "owner_only": self.OwnerOnlyRights,
            "owner_write_only": self.OwnerWriteRights,
            "authenticated": self.AuthenticatedRights,
        }.get(rights)
        if not cls:
            return False
        return cls.authorized(self, user, path, perm)
