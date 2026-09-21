class SearchResult(list):
    def __init__(self, values=(), telemetry=None):
        super().__init__(values)
        self.telemetry = telemetry or {}
