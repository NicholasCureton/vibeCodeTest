"""
FILE: memory/project_state.py
ROLE: Project State Management (PROJECT.md)

DESCRIPTION:
    Manages project state for cross-session continuity.
    When context fills up, this state persists so the agent
    can continue where it left off.

    Think of it as "onboarding documentation for the agent"
    that gets updated as the project progresses.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path


class ProjectState:
    """
    Manages PROJECT.md for cross-session continuity.

    The PROJECT.md file contains:
    - Project goal and status
    - What's done / in progress / next
    - Decisions log
    - Known issues
    - What to avoid
    """

    def __init__(self, filename: str = "state/PROJECT.md"):
        """
        Initialize project state.

        Args:
            filename: Path to PROJECT.md file
        """
        self.filename = filename
        self._state: Dict[str, Any] = {
            "name": "",
            "status": "Unknown",
            "last_updated": "",
            "goal": "",
            "roadmap": [],
            "done": [],
            "in_progress": [],
            "next": [],
            "decisions": [],
            "issues": [],
            "avoid": [],
            "files_changed": []
        }

    def load(self) -> bool:
        """
        Load state from PROJECT.md.

        Returns:
            True if file exists and was loaded
        """
        if not os.path.exists(self.filename):
            return False

        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                content = f.read()

            self._parse_markdown(content)
            return True

        except IOError:
            return False

    def save(self) -> bool:
        """
        Save state to PROJECT.md.

        Returns:
            True on success
        """
        # Ensure directory exists
        Path(self.filename).parent.mkdir(parents=True, exist_ok=True)

        self._state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        content = self._generate_markdown()

        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except IOError as e:
            print(f"[project_state] Could not save: {e}")
            return False

    def _parse_markdown(self, content: str) -> None:
        """Parse PROJECT.md content into state dict."""
        lines = content.split("\n")
        current_section = None
        current_list = []

        for line in lines:
            line = line.strip()

            # Section headers
            if line.startswith("# "):
                self._state["name"] = line[2:].strip()
            elif line.startswith("## "):
                # Save previous section
                if current_section and current_list:
                    self._state[current_section] = current_list
                current_section = self._map_section(line[3:].strip().lower())
                current_list = []
            elif line.startswith("- [x] "):
                current_list.append({"done": True, "item": line[6:]})
            elif line.startswith("- [ ] "):
                current_list.append({"done": False, "item": line[6:]})
            elif line.startswith("- "):
                current_list.append(line[2:])

        # Save last section
        if current_section and current_list:
            self._state[current_section] = current_list

    def _map_section(self, header: str) -> Optional[str]:
        """Map markdown header to state key."""
        mapping = {
            "status": "status",
            "goal": "goal",
            "roadmap": "roadmap",
            "what's done": "done",
            "what's in progress": "in_progress",
            "what's next": "next",
            "decisions": "decisions",
            "known issues": "issues",
            "what to avoid": "avoid",
            "files changed": "files_changed"
        }
        return mapping.get(header)

    def _generate_markdown(self) -> str:
        """Generate PROJECT.md content from state."""
        lines = []

        # Header
        lines.append(f"# {self._state.get('name', 'PROJECT')}")
        lines.append("")

        # Status
        lines.append("## STATUS")
        lines.append(f"State: {self._state.get('status', 'Unknown')}")
        lines.append(f"Last Updated: {self._state.get('last_updated', '')}")
        lines.append("")

        # Goal
        goal = self._state.get("goal", "")
        if goal:
            lines.append("## GOAL")
            lines.append(goal)
            lines.append("")

        # Roadmap
        roadmap = self._state.get("roadmap", [])
        if roadmap:
            lines.append("## ROADMAP")
            for item in roadmap:
                if isinstance(item, dict):
                    checked = "x" if item.get("done") else " "
                    lines.append(f"- [{checked}] {item.get('item', '')}")
                else:
                    lines.append(f"- {item}")
            lines.append("")

        # Done
        done = self._state.get("done", [])
        if done:
            lines.append("## WHAT'S DONE")
            for item in done:
                if isinstance(item, dict):
                    lines.append(f"- [x] {item.get('item', item)}")
                else:
                    lines.append(f"- [x] {item}")
            lines.append("")

        # In Progress
        in_progress = self._state.get("in_progress", [])
        if in_progress:
            lines.append("## WHAT'S IN PROGRESS")
            for item in in_progress:
                lines.append(f"- [ ] {item}")
            lines.append("")

        # Next
        next_items = self._state.get("next", [])
        if next_items:
            lines.append("## WHAT'S NEXT")
            for i, item in enumerate(next_items, 1):
                lines.append(f"{i}. {item}")
            lines.append("")

        # Decisions
        decisions = self._state.get("decisions", [])
        if decisions:
            lines.append("## DECISIONS LOG")
            lines.append("| Decision | Choice | Reason |")
            lines.append("|----------|--------|--------|")
            for item in decisions:
                if isinstance(item, dict):
                    lines.append(f"| {item.get('decision', '')} | {item.get('choice', '')} | {item.get('reason', '')} |")
                elif isinstance(item, list) and len(item) >= 3:
                    lines.append(f"| {item[0]} | {item[1]} | {item[2]} |")
            lines.append("")

        # Issues
        issues = self._state.get("issues", [])
        if issues:
            lines.append("## KNOWN ISSUES / BLOCKERS")
            for item in issues:
                lines.append(f"- {item}")
            lines.append("")

        # Avoid
        avoid = self._state.get("avoid", [])
        if avoid:
            lines.append("## WHAT TO AVOID")
            for item in avoid:
                lines.append(f"- {item}")
            lines.append("")

        # Files Changed
        files = self._state.get("files_changed", [])
        if files:
            lines.append("## FILES CHANGED THIS SESSION")
            for item in files:
                lines.append(f"- {item}")
            lines.append("")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def set_name(self, name: str) -> None:
        """Set project name."""
        self._state["name"] = name

    def set_status(self, status: str) -> None:
        """Set project status."""
        self._state["status"] = status

    def set_goal(self, goal: str) -> None:
        """Set project goal."""
        self._state["goal"] = goal

    def add_done(self, item: str) -> None:
        """Add item to done list."""
        self._state["done"].append({"done": True, "item": item})

    def add_in_progress(self, item: str) -> None:
        """Add item to in-progress list."""
        self._state["in_progress"].append(item)

    def add_next(self, item: str) -> None:
        """Add item to next list."""
        self._state["next"].append(item)

    def add_decision(self, decision: str, choice: str, reason: str) -> None:
        """Add decision to log."""
        self._state["decisions"].append({
            "decision": decision,
            "choice": choice,
            "reason": reason
        })

    def add_issue(self, issue: str) -> None:
        """Add issue to list."""
        self._state["issues"].append(issue)

    def add_avoid(self, item: str) -> None:
        """Add item to avoid list."""
        self._state["avoid"].append(item)

    def add_file_changed(self, file: str, description: str = "") -> None:
        """Add file to changed list."""
        if description:
            self._state["files_changed"].append(f"{file} - {description}")
        else:
            self._state["files_changed"].append(file)

    def clear_files_changed(self) -> None:
        """Clear files changed list (start of new session)."""
        self._state["files_changed"] = []

    def get_context_summary(self) -> str:
        """
        Get a summary for LLM context.

        Returns:
            Condensed summary of project state
        """
        lines = [
            f"PROJECT: {self._state.get('name', 'Unknown')}",
            f"STATUS: {self._state.get('status', 'Unknown')}",
            f"GOAL: {self._state.get('goal', 'Not defined')}",
            "",
            "DONE:",
        ]

        for item in self._state.get("done", [])[:5]:  # Last 5
            if isinstance(item, dict):
                lines.append(f"  - {item.get('item', '')}")
            else:
                lines.append(f"  - {item}")

        lines.append("")
        lines.append("IN PROGRESS:")
        for item in self._state.get("in_progress", [])[:3]:
            lines.append(f"  - {item}")

        lines.append("")
        lines.append("NEXT:")
        for item in self._state.get("next", [])[:3]:
            lines.append(f"  - {item}")

        return "\n".join(lines)
