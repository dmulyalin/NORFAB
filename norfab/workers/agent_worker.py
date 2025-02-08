import json
import logging
import sys
import importlib.metadata
from norfab.core.worker import NFPWorker, Result

log = logging.getLogger(__name__)

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama.llms import OllamaLLM

    HAS_LIBS = True
except ImportError:
    HAS_LIBS = False
    log.error("AI Agent Worker - failed to import needed libraries.")


class AgentWorker(NFPWorker):
    """
    NORFAB AI Agent Worker

    :param broker: broker URL to connect to
    :param service: name of the service with worker belongs to
    :param worker_name: name of this worker
    :param exit_event: if set, worker need to stop/exit
    :param init_done_event: event to set when worker done initializing
    :param log_level: logging level of this worker
    """

    def __init__(
        self,
        inventory,
        broker: str,
        worker_name: str,
        service: str = b"agent",
        exit_event=None,
        init_done_event=None,
        log_level: str = "WARNING",
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, service, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event

        # get inventory from broker
        self.agent_inventory = self.load_inventory()
        self.llm_model = self.agent_inventory.get("llm_model", "llama3.1:8b")
        self.llm_temperature = self.agent_inventory.get("llm_temperature", 0.5)
        self.llm_base_url = self.agent_inventory.get(
            "llm_base_url", "http://127.0.0.1:11434"
        )
        self.llm_flavour = self.agent_inventory.get("llm_flavour", "ollama")

        if self.llm_flavour == "ollama":
            self.llm = OllamaLLM(
                model=self.llm_model,
                temperature=self.llm_temperature,
                base_url=self.llm_base_url,
            )

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def worker_exit(self):
        pass

    def get_version(self):
        """
        Produce Python packages version report
        """
        libs = {
            "norfab": "",
            "langchain": "",
            "langchain-community": "",
            "langchain-core": "",
            "langchain-ollama": "",
            "ollama": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
            "llm_model": self.llm_model,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(result=libs)

    def get_inventory(self):
        return Result(result=self.agent_inventory)

    def get_status(self):
        return Result(result="OK")

    def _chat_ollama(self, user_input, template=None) -> str:
        """
        Handles the chat interaction with Ollama LLM.
        """
        self.event(f"Received user input '{user_input[:50]}..'")
        ret = Result(task=f"{self.name}:chat")
        template = (
            template
            or """Question: {user_input}; Answer: Let's think step by step. Provide answer in markdown format."""
        )
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | self.llm

        self.event("Thinking...")
        ret.result = chain.invoke({"user_input": user_input})

        self.event("Done thinking, sending result back to user")

        return ret

    def chat(self, user_input, template=None) -> str:
        """
        Handles the chat interaction with the user by processing the input through a language model.

        :param user_input: The input provided by the user.
        :param template: A template string for formatting the prompt. Defaults to
            this string: 'Question: {user_input}; Answer: Let's think step by step.
            Provide answer in markdown format.'
        :returns: language model's response
        """
        if self.llm_flavour == "ollama":
            return self._chat_ollama(user_input, template)
        else:
            raise Exception(f"Unsupported llm flavour {self.llm_flavour}")
