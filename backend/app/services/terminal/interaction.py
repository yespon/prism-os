import re


class InteractionDetector:
    def __init__(self):
        # Basic patterns for password, sudo, yes/no
        self.password_pattern = re.compile(r"(?i)(password|passphrase).*:.*$")
        self.sudo_pattern = re.compile(r"(?i)\[sudo\] password for .*:.*$")
        self.yes_no_pattern = re.compile(r"(?i)\(yes/no.*?\).*$")
        
        # Basic patterns for TUI and pagers
        self.tui_pattern = re.compile(r"\x1b\[\?1049h|\x1b\[\?1h") # typical escape sequences for alternate screen buffer

    def detect(self, chunk: str) -> dict | None:
        """
        Analyze a chunk of output to detect if interaction is required.
        Returns a dictionary with interaction details or None.
        """
        if self.sudo_pattern.search(chunk):
            return {
                "type": "waiting_input",
                "interaction_type": "password",
                "prompt_hint": "Please enter sudo password",
                "options": []
            }
            
        if self.password_pattern.search(chunk):
            return {
                "type": "waiting_input",
                "interaction_type": "password",
                "prompt_hint": "Please enter password",
                "options": []
            }
            
        if self.yes_no_pattern.search(chunk):
            return {
                "type": "waiting_input",
                "interaction_type": "yes_no",
                "prompt_hint": "Please answer yes or no",
                "options": ["yes", "no"]
            }
            
        if self.tui_pattern.search(chunk):
            return {
                "type": "waiting_input",
                "interaction_type": "tui",
                "prompt_hint": "TUI detected. Full terminal access required.",
                "options": []
            }

        return None

interaction_detector = InteractionDetector()
