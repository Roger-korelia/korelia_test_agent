"""Test simple para verificar que el agente funciona correctamente."""
import sys
import os
from pathlib import Path

# Asegurar que los imports funcionen
sys.path.insert(0, str(Path(__file__).parent))

from apps.backend.agent import create_agent_graph


def test_agent_basic():
    """Test básico para verificar que el agente se crea y puede procesar un mensaje simple."""
    print("=" * 60)
    print("Test: Crear agente y procesar mensaje simple")
    print("=" * 60)
    
    try:
        # 1. Crear el agente
        print("\n[1/3] Creando agente...")
        agent = create_agent_graph()
        print(f"✓ Agente creado: {type(agent)}")
        
        # 2. Preparar mensaje de prueba simple
        print("\n[2/3] Preparando mensaje de prueba...")
        test_message = {
            "messages": [
                {
                    "role": "user",
                    "content": "Hola, ¿puedes decirme qué herramientas tienes disponibles?"
                }
            ]
        }
        print(f"✓ Mensaje preparado: {test_message['messages'][0]['content'][:50]}...")
        
        # 3. Invocar el agente (sin stream para test simple)
        print("\n[3/3] Invocando agente...")
        print("(Esto puede tardar unos segundos...)")
        
        result = agent.invoke(test_message)
        
        print("\n" + "=" * 60)
        print("✓ TEST EXITOSO")
        print("=" * 60)
        print(f"\nRespuesta del agente:")
        print("-" * 60)
        
        # Mostrar la última respuesta del agente
        if isinstance(result, dict) and "messages" in result:
            last_msg = result["messages"][-1]
            if hasattr(last_msg, "content"):
                print(last_msg.content)
            else:
                print(str(last_msg))
        else:
            print(str(result)[:500])
            
        return True
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("✗ TEST FALLIDO")
        print("=" * 60)
        print(f"\nError: {type(e).__name__}: {e}")
        import traceback
        print("\nTraceback completo:")
        traceback.print_exc()
        return False


def test_agent_with_tool():
    """Test para verificar que el agente puede usar herramientas."""
    print("\n" + "=" * 60)
    print("Test: Agente usando herramientas")
    print("=" * 60)
    
    try:
        agent = create_agent_graph()
        
        # Mensaje que debería activar una herramienta
        test_message = {
            "messages": [
                {
                    "role": "user",
                    "content": "Lista todas las herramientas disponibles y qué hacen"
                }
            ]
        }
        
        print("\nInvocando agente con mensaje que requiere herramientas...")
        result = agent.invoke(test_message)
        
        print("\n✓ Test de herramientas completado")
        print(f"Resultado tipo: {type(result)}")
        
        if isinstance(result, dict) and "messages" in result:
            print(f"Número de mensajes: {len(result['messages'])}")
            for i, msg in enumerate(result["messages"]):
                print(f"\nMensaje {i+1}: {type(msg).__name__}")
                if hasattr(msg, "content"):
                    content = msg.content
                    print(f"  Contenido: {content[:200]}..." if len(content) > 200 else f"  Contenido: {content}")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error en test de herramientas: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🧪 Iniciando tests del agente LangGraph\n")
    
    # Test básico
    success1 = test_agent_basic()
    
    # Test con herramientas (opcional, más lento)
    if success1:
        print("\n¿Ejecutar test con herramientas? (puede tardar y consumir tokens)")
        # Descomentar para ejecutar:
        # success2 = test_agent_with_tool()
    
    print("\n" + "=" * 60)
    if success1:
        print("✓ Tests básicos pasados")
    else:
        print("✗ Tests fallaron - revisa los errores arriba")
    print("=" * 60 + "\n")