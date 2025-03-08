import json
import logging
import sys
import importlib.metadata
from norfab.core.worker import NFPWorker, Result
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

SERVICE = "agent"

log = logging.getLogger(__name__)


class AgentWorker(NFPWorker):
    """
    This class represents a worker that interacts with a language model to
    handle various tasks such as chatting with users, retrieving inventory,
    and producing version reports of Python packages.

    Args:
        inventory: The inventory object to be used by the worker.
        broker (str): The broker URL to connect to.
        worker_name (str): The name of this worker.
        exit_event: An event that, if set, indicates the worker needs to stop/exit.
        init_done_event: An event to set when the worker has finished initializing.
        log_level (str): The logging level of this worker. Defaults to "WARNING".
        log_queue (object): The logging queue object.

    Attributes:
        agent_inventory: The inventory loaded from the broker.
        llm_model (str): The language model to be used. Defaults to "llama3.1:8b".
        llm_temperature (float): The temperature setting for the language model. Defaults to 0.5.
        llm_base_url (str): The base URL for the language model. Defaults to "http://127.0.0.1:11434".
        llm_flavour (str): The flavour of the language model. Defaults to "ollama".
        llm: The language model instance.

    Methods:
        worker_exit(): Placeholder method for worker exit logic.
        get_version(): Produces a report of the versions of Python packages.
        get_inventory(): Returns the agent's inventory.
        get_status(): Returns the status of the worker.
        _chat_ollama(user_input, template=None) -> str: Handles the chat interaction with the Ollama LLM.
        chat(user_input, template=None) -> str: Handles the chat interaction with the user by processing the input through a language model.
    """

    def __init__(
        self,
        inventory,
        broker: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = "WARNING",
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
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
        Generate a report of the versions of specific Python packages and system information.
        This method collects the version information of several Python packages and system details,
        including the Python version, platform, and a specified language model.

        Returns:
            Result: An object containing a dictionary with the package names as keys and their
                    respective version numbers as values. If a package is not found, its version
                    will be an empty string.
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
        """
        NorFab task to retrieve the agent's inventory.

        Returns:
            Result: An instance of the Result class containing the agent's inventory.
        """
        return Result(result=self.agent_inventory)

    def get_status(self):
        """
        NorFab Task that retrieves the status of the agent worker.

        Returns:
            Result: An object containing the status result with a value of "OK".
        """
        return Result(result="OK")

    def _chat_ollama(self, user_input, template=None) -> str:
        """
        NorFab Task that handles the chat interaction with Ollama LLM.

        Args:
            user_input (str): The input provided by the user.
            template (str, optional): The template for generating the prompt. Defaults to a predefined template.

        Returns:
            str: The result of the chat interaction.
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
        NorFab Task that handles the chat interaction with the user by processing the input through a language model.

        Args:
            user_input (str): The input provided by the user.
            template (str, optional): A template string for formatting the prompt. Defaults to

        Returns:
            str: Language model's response.

        Raises:
            Exception: If the llm_flavour is unsupported.
        """
        if self.llm_flavour == "ollama":
            return self._chat_ollama(user_input, template)
        else:
            raise Exception(f"Unsupported llm flavour {self.llm_flavour}")
