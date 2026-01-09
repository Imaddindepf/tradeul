"""
Gemini Client for AI Agent
"""

import os
import re
import asyncio
from typing import AsyncIterator, Dict, List, Optional, Any
from dataclasses import dataclass
import structlog
from datetime import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor

from google import genai
from google.genai import types

from .prompts import SystemPrompts

# Thread pool para ejecutar llamadas sincronas de Gemini
_executor = ThreadPoolExecutor(max_workers=4)

logger = structlog.get_logger(__name__)


@dataclass
class Message:
    """Mensaje en la conversación"""
    role: str  # 'user' o 'assistant'
    content: str


@dataclass
class LastResult:
    """Último resultado mostrado al usuario (para refinamiento)"""
    title: str
    row_count: int
    columns: List[str]
    sample_symbols: List[str]  # Primeros 5 símbolos
    code: str


@dataclass
class LLMResponse:
    """Respuesta del LLM"""
    text: str
    code_blocks: List[str]
    has_code: bool
    finish_reason: Optional[str] = None


class GeminiClient:
    """
    Cliente para interactuar con Gemini.
    
    Genera respuestas y código DSL basado en las consultas del usuario.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el cliente de Gemini.
        
        Args:
            api_key: API key de Google AI (o usa GOOGLE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY es requerido")
        
        self.client = genai.Client(api_key=self.api_key)
        self.model = "gemini-2.5-flash"  # Model with thinking capabilities
        self.model_thinking = "gemini-2.5-flash"  # For queries requiring reasoning
        self.prompts = SystemPrompts()
        
        # Historial de conversación por usuario
        self.conversations: Dict[str, List[Message]] = {}
        
        # Último resultado por conversación (para refinamiento)
        self.last_results: Dict[str, LastResult] = {}
    
    async def generate_response(
        self,
        user_message: str,
        conversation_id: str,
        market_context: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Genera una respuesta basada en el mensaje del usuario.
        
        Args:
            user_message: Mensaje del usuario
            conversation_id: ID de la conversación
            market_context: Contexto del mercado actual
        
        Returns:
            LLMResponse con texto y código
        """
        # Obtener o crear historial
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        
        history = self.conversations[conversation_id]
        
        # Construir el system prompt con contexto actual
        system_prompt = self.prompts.get_main_prompt()
        
        if market_context:
            context_str = self.prompts.get_context_injection(
                market_session=market_context.get('session', 'UNKNOWN'),
                current_time_et=market_context.get('time_et', datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S')),
                scanner_count=market_context.get('scanner_count', 0),
                category_stats=market_context.get('category_stats')
            )
            system_prompt = system_prompt.replace("## CONTEXTO ACTUAL", context_str)
        
        # REFINAMIENTO: Inyectar contexto del último resultado
        last_result = self.last_results.get(conversation_id)
        if last_result:
            refinement_context = f"""

## RESULTADO ANTERIOR (para refinamiento)
El usuario está viendo una tabla "{last_result.title}" con {last_result.row_count} filas.
Columnas: {', '.join(last_result.columns)}
Símbolos de ejemplo: {', '.join(last_result.sample_symbols)}

Si el usuario pide "filtrar", "mostrar solo", "de esos" o similar, aplica el filtro sobre estos datos.
Puedes usar el código anterior como base:
```python
{last_result.code}
```
"""
            system_prompt += refinement_context
        
        # Construir contenido para Gemini
        contents = []
        
        # System instruction como primer mensaje
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=f"[SYSTEM]\n{system_prompt}")]
        ))
        contents.append(types.Content(
            role="model",
            parts=[types.Part(text="Entendido. Soy el asistente financiero de TradeUL. Estoy listo para ayudarte a analizar el mercado usando nuestro DSL de consultas.")]
        ))
        
        # Agregar historial
        for msg in history[-10:]:  # Últimos 10 mensajes
            contents.append(types.Content(
                role="user" if msg.role == "user" else "model",
                parts=[types.Part(text=msg.content)]
            ))
        
        # Agregar mensaje actual
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=user_message)]
        ))
        
        try:
            # Llamar a Gemini
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    top_p=0.95,
                    max_output_tokens=4096,
                )
            )
            
            # Extraer texto
            response_text = response.text if response.text else ""
            
            # Extraer bloques de código Python
            code_blocks = self._extract_code_blocks(response_text)
            
            # Actualizar historial
            history.append(Message(role="user", content=user_message))
            history.append(Message(role="assistant", content=response_text))
            
            # Mantener historial manejable
            if len(history) > 20:
                self.conversations[conversation_id] = history[-20:]
            
            return LLMResponse(
                text=response_text,
                code_blocks=code_blocks,
                has_code=len(code_blocks) > 0,
                finish_reason=response.candidates[0].finish_reason.name if response.candidates else None
            )
        
        except Exception as e:
            logger.error("gemini_error", error=str(e))
            return LLMResponse(
                text=f"Error al procesar tu solicitud: {str(e)}",
                code_blocks=[],
                has_code=False
            )
    
    async def generate_response_stream(
        self,
        user_message: str,
        conversation_id: str,
        market_context: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[str]:
        """
        Genera una respuesta en streaming.
        
        Args:
            user_message: Mensaje del usuario
            conversation_id: ID de la conversación
            market_context: Contexto del mercado actual
        
        Yields:
            Fragmentos de texto de la respuesta
        """
        # Preparar historial
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        
        history = self.conversations[conversation_id]
        
        system_prompt = self.prompts.get_main_prompt()
        
        if market_context:
            context_str = self.prompts.get_context_injection(
                market_session=market_context.get('session', 'UNKNOWN'),
                current_time_et=market_context.get('time_et', datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S')),
                scanner_count=market_context.get('scanner_count', 0),
                category_stats=market_context.get('category_stats')
            )
            system_prompt = system_prompt.replace("## CONTEXTO ACTUAL", context_str)
        
        # REFINAMIENTO: Inyectar contexto del ultimo resultado
        last_result = self.last_results.get(conversation_id)
        if last_result:
            refinement_context = f"""

## RESULTADO ANTERIOR (para refinamiento)
El usuario esta viendo una tabla "{last_result.title}" con {last_result.row_count} filas.
Columnas: {', '.join(last_result.columns)}
Simbolos de ejemplo: {', '.join(last_result.sample_symbols)}

Si el usuario pide "filtrar", "mostrar solo", "de esos" o similar, aplica el filtro sobre estos datos.
"""
            system_prompt += refinement_context
        
        contents = []
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=f"[SYSTEM]\n{system_prompt}")]
        ))
        contents.append(types.Content(
            role="model",
            parts=[types.Part(text="Entendido. Soy el asistente financiero de TradeUL.")]
        ))
        
        for msg in history[-10:]:
            contents.append(types.Content(
                role="user" if msg.role == "user" else "model",
                parts=[types.Part(text=msg.content)]
            ))
        
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=user_message)]
        ))
        
        try:
            # El SDK de genai usa generadores sincronos, ejecutamos en thread pool
            # y usamos una queue async para el streaming
            queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
            loop = asyncio.get_event_loop()
            
            def _generate_sync():
                """Ejecuta la generacion sincrona y pone chunks en la queue"""
                try:
                    for chunk in self.client.models.generate_content_stream(
                        model=self.model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            temperature=0.7,
                            top_p=0.95,
                            max_output_tokens=4096,
                        )
                    ):
                        if chunk.text:
                            # Poner chunk en queue de forma thread-safe
                            loop.call_soon_threadsafe(queue.put_nowait, chunk.text)
                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait, f"\n\nError: {str(e)}")
                finally:
                    # Señal de fin
                    loop.call_soon_threadsafe(queue.put_nowait, None)
            
            # Iniciar generacion en thread separado
            future = loop.run_in_executor(_executor, _generate_sync)
            
            full_response = ""
            
            # Consumir chunks de la queue
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                full_response += chunk
                yield chunk
            
            # Esperar a que termine el thread
            await future
            
            # Actualizar historial despues del streaming
            history.append(Message(role="user", content=user_message))
            history.append(Message(role="assistant", content=full_response))
            
            if len(history) > 20:
                self.conversations[conversation_id] = history[-20:]
        
        except Exception as e:
            logger.error("gemini_stream_error", error=str(e))
            yield f"\n\nError: {str(e)}"
    
    def _extract_code_blocks(self, text: str) -> List[str]:
        """
        Extrae bloques de código Python del texto.
        
        Args:
            text: Texto con posibles bloques de código
        
        Returns:
            Lista de bloques de código
        """
        # Patrón para bloques ```python ... ``` o ``` ... ```
        pattern = r'```(?:python)?\s*(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        
        # Filtrar solo código que parece ser DSL (tiene Query, col, display_table, etc.)
        dsl_keywords = ['Query', 'col', 'display_table', 'create_chart', 'print_stats', '.execute()']
        
        valid_blocks = []
        for block in matches:
            block = block.strip()
            if any(kw in block for kw in dsl_keywords):
                valid_blocks.append(block)
        
        return valid_blocks
    
    async def generate_with_thinking(
        self,
        prompt: str,
        on_thought: callable = None,
        max_tokens: int = 4096
    ) -> tuple[str, List[str]]:
        """
        Generate content with thinking mode enabled.
        Returns the final response and list of thought summaries.
        
        Args:
            prompt: The prompt to send
            on_thought: Optional callback for streaming thoughts
            max_tokens: Maximum output tokens
            
        Returns:
            Tuple of (response_text, thoughts_list)
        """
        thoughts = []
        response_text = ""
        
        try:
            # Enable thinking with ThinkingConfig
            response = self.client.models.generate_content(
                model=self.model_thinking,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                )],
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=max_tokens,
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=True
                    )
                )
            )
            
            # Extract thoughts and response from parts
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'thought') and part.thought:
                        # This is a thought part
                        thought_text = part.text if hasattr(part, 'text') else str(part)
                        thoughts.append(thought_text)
                        if on_thought:
                            await on_thought(thought_text)
                    elif hasattr(part, 'text'):
                        # Regular response part
                        response_text += part.text
            
            return response_text, thoughts
            
        except Exception as e:
            logger.error("generate_with_thinking_error", error=str(e))
            return f"Error: {str(e)}", []
    
    async def stream_with_thinking(
        self,
        prompt: str,
        on_thought: callable = None,
        on_text: callable = None,
        max_tokens: int = 4096
    ) -> tuple[str, List[str]]:
        """
        Stream content generation with thinking mode.
        Thoughts are streamed as they become available.
        
        Args:
            prompt: The prompt to send
            on_thought: Callback for thought chunks
            on_text: Callback for response text chunks
            max_tokens: Maximum output tokens
            
        Returns:
            Tuple of (full_response, all_thoughts)
        """
        thoughts = []
        response_text = ""
        current_thought = ""
        
        try:
            # Stream with thinking enabled
            for chunk in self.client.models.generate_content_stream(
                model=self.model_thinking,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                )],
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=max_tokens,
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=True
                    )
                )
            ):
                if chunk.candidates and chunk.candidates[0].content:
                    for part in chunk.candidates[0].content.parts:
                        if hasattr(part, 'thought') and part.thought:
                            thought_chunk = part.text if hasattr(part, 'text') else ""
                            current_thought += thought_chunk
                            if on_thought and thought_chunk:
                                await on_thought(thought_chunk)
                        elif hasattr(part, 'text'):
                            text_chunk = part.text
                            response_text += text_chunk
                            if on_text and text_chunk:
                                await on_text(text_chunk)
                
                # Check for thought completion
                if current_thought and (not chunk.candidates or 
                    not any(hasattr(p, 'thought') and p.thought 
                            for p in chunk.candidates[0].content.parts if chunk.candidates[0].content)):
                    thoughts.append(current_thought)
                    current_thought = ""
            
            # Add any remaining thought
            if current_thought:
                thoughts.append(current_thought)
            
            return response_text, thoughts
            
        except Exception as e:
            logger.error("stream_with_thinking_error", error=str(e))
            return f"Error: {str(e)}", thoughts
    
    async def generate_json(
        self,
        prompt: str,
        max_tokens: int = 1024
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a JSON response from the LLM.
        Used for structured extraction like temporal expressions.
        
        Args:
            prompt: Prompt requesting JSON output
            max_tokens: Maximum tokens in response
        
        Returns:
            Parsed JSON dict or None on error
        """
        import json
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                )],
                config=types.GenerateContentConfig(
                    temperature=0.1,  # Very low for structured output
                    max_output_tokens=max_tokens,
                )
            )
            
            response_text = response.text if response.text else ""
            
            # Extract the LARGEST JSON object from response (not nested sub-objects)
            # Use a greedy match that handles nested braces
            json_matches = []
            depth = 0
            start = -1
            for i, char in enumerate(response_text):
                if char == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0 and start >= 0:
                        json_matches.append(response_text[start:i+1])
                        start = -1
            
            # Return the largest JSON object (most likely the main one)
            if json_matches:
                largest = max(json_matches, key=len)
                return json.loads(largest)
            
            # Try parsing the whole response
            return json.loads(response_text.strip())
        
        except json.JSONDecodeError as e:
            logger.warning("json_parse_error", error=str(e), response=response_text[:200])
            return None
        except Exception as e:
            logger.warning("generate_json_error", error=str(e))
            return None
    
    async def fix_code(
        self,
        original_code: str,
        error_message: str,
        conversation_id: str = "auto_heal"
    ) -> str:
        """
        Auto-heal: Pide al LLM que corrija código que falló.
        
        Args:
            original_code: Código que falló
            error_message: Mensaje de error
            conversation_id: ID de conversación
        
        Returns:
            Código corregido
        """
        fix_prompt = f"""El siguiente código DSL generó un error. Corrige SOLO el código sin explicaciones.

CÓDIGO ORIGINAL:
```python
{original_code}
```

ERROR:
{error_message}

INSTRUCCIONES:
1. Analiza el error
2. Corrige el código usando SOLO funciones válidas del DSL
3. Retorna SOLO el código corregido entre ```python y ```
4. NO uses funciones inventadas - revisa las permitidas:
   - Operadores: >= <= > < == !=
   - Métodos de col(): .between(a,b), .isin([...]), .contains('x'), .is_null(), .not_null()

CÓDIGO CORREGIDO:"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part(text=fix_prompt)]
                )],
                config=types.GenerateContentConfig(
                    temperature=0.3,  # Más determinístico para correcciones
                    max_output_tokens=2048,
                )
            )
            
            response_text = response.text if response.text else ""
            code_blocks = self._extract_code_blocks(response_text)
            
            if code_blocks:
                return code_blocks[0]
            return original_code  # Si no puede corregir, devolver original
        
        except Exception as e:
            logger.error("auto_heal_error", error=str(e))
            return original_code
    
    def set_last_result(
        self,
        conversation_id: str,
        title: str,
        row_count: int,
        columns: List[str],
        sample_symbols: List[str],
        code: str
    ) -> None:
        """
        Guarda el último resultado para permitir refinamiento.
        
        Args:
            conversation_id: ID de la conversación
            title: Título de la tabla/gráfico
            row_count: Número de filas
            columns: Lista de columnas
            sample_symbols: Primeros símbolos (para contexto)
            code: Código DSL ejecutado
        """
        self.last_results[conversation_id] = LastResult(
            title=title,
            row_count=row_count,
            columns=columns,
            sample_symbols=sample_symbols[:5],  # Máximo 5 símbolos
            code=code
        )
    
    def clear_conversation(self, conversation_id: str) -> None:
        """Limpia el historial de una conversación"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
        if conversation_id in self.last_results:
            del self.last_results[conversation_id]
    
    def get_conversation_history(self, conversation_id: str) -> List[Message]:
        """Obtiene el historial de una conversación"""
        return self.conversations.get(conversation_id, [])

