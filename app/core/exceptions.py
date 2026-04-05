class PatientNotFoundError(Exception):
    pass


class NoteNotFoundError(Exception):
    pass


class ProviderEmailConflictError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


class InvalidCSVError(Exception):
    pass
