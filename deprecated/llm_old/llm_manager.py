"""Centralized LLM manager using LangChain."""

from typing import Optional, Union
from config import settings
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

# For instrumentation (using arize. accessible at https://app.arize.com/)
if settings.arize_space_id and settings.arize_api_key:
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from arize.otel import register
    tracer_provider = register(
        space_id=settings.arize_space_id,
        api_key=settings.arize_api_key,
        project_name=settings.arize_project_name,
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
else:
    print("⚠️  Arize monitoring disabled (ARIZE_SPACE_ID / ARIZE_API_KEY not set)")
     

class LLMManager:
    """Singleton manager for LLM instances and chains."""
    
    _instance: Optional['LLMManager'] = None
    _chat_llm: Optional[Union[ChatGroq, ChatGoogleGenerativeAI]] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._chat_llm is None:
            self._initialize_llm()
    
    def _initialize_llm(self):
        """Initialize LangChain LLM instance based on provider setting."""
        provider = settings.llm_provider.lower().strip()
        
        if provider == "groq":
            api_key = settings.groq_api_key
            if not api_key:
                raise ValueError("GROQ_API_KEY not found in environment variables")
            
            self._chat_llm = ChatGroq(
                model=settings.llm_model,
                temperature=settings.llm_convo_temperature,
                groq_api_key=api_key
            )
            print(f"[OK] Initialized Groq LLM with model: {settings.llm_model}")
            
        elif provider == "gemini":
            api_key = settings.gemini_api_key
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found in environment variables")
            
            self._chat_llm = ChatGoogleGenerativeAI(
                model=settings.llm_model,
                temperature=settings.llm_convo_temperature,
                google_api_key=api_key
            )
            print(f"[OK] Initialized Gemini LLM with model: {settings.llm_model}")
            
        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                "Supported providers are: 'groq', 'gemini'"
            )
    
    @property
    def chat_llm(self) -> Union[ChatGroq, ChatGoogleGenerativeAI]:
        """Get the chat LLM instance."""
        if self._chat_llm is None:
            self._initialize_llm()
        return self._chat_llm
    
    def get_chat_llm(self, temperature: Optional[float] = None) -> Union[ChatGroq, ChatGoogleGenerativeAI]:
        """Get a chat LLM with custom temperature."""
        provider = settings.llm_provider.lower().strip()
        
        if temperature is None:
            temperature = settings.llm_convo_temperature
        
        if provider == "groq":
            api_key = settings.groq_api_key
            if not api_key:
                raise ValueError("GROQ_API_KEY not found in environment variables")
            return ChatGroq(
                model=settings.llm_model,
                temperature=temperature,
                groq_api_key=api_key
            )
            
        elif provider == "gemini":
            api_key = settings.gemini_api_key
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found in environment variables")
            return ChatGoogleGenerativeAI(
                model=settings.llm_model,
                temperature=temperature,
                google_api_key=api_key
            )
            
        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                "Supported providers are: 'groq', 'gemini'"
            )
    
    def create_structured_chain(self, system_prompt: str, pydantic_model, temperature: float = 0.0):
        """
        Create a LangChain structured output chain using provider's native JSON mode.
        
        Args:
            system_prompt: System prompt for the LLM
            pydantic_model: Pydantic model for structured output
            temperature: Temperature for generation
            
        Returns:
            Runnable chain that outputs pydantic_model instances
        """
        # Get LLM instance
        llm = self.get_chat_llm(temperature=temperature)
        
        # For Groq, use json_schema method for native structured output
        # For Gemini, use default method (json_mode or function_calling)
        provider = settings.llm_provider.lower().strip()
        
        if provider == "groq":
            # Explicitly use json_schema method for Groq's native structured output
            structured_llm = llm.with_structured_output(
                pydantic_model,
                method="json_schema",
                include_raw=False
            )
        else:
            # For Gemini and others, let LangChain choose the best method
            structured_llm = llm.with_structured_output(
                pydantic_model,
                include_raw=False
            )
        
        # Create a simple prompt template without format_instructions
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{input}")
        ])
        
        chain = prompt | structured_llm
        return chain


# Singleton instance
llm_manager = LLMManager()
