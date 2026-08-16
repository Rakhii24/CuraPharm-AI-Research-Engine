"""Orchestration entry point for the Phase 5 analysis service."""


class AnalysisOrchestrator:
    """Delegate one process analysis without knowing the provider implementation."""

    def __init__(self, analysis_service):
        self.analysis_service = analysis_service

    def analyze(self, process_id: int):
        """Analyze one process using already stored research evidence."""
        return self.analysis_service.analyze_process(process_id)
