import os
from .ast import CobolProgram

class StreamingEmitter:
    """ Generates FastStream Kafka consumers for the COBOL execution logic. """
    def __init__(self, program: CobolProgram):
        self.program = program

    def emit(self, output_dir: str):
        routes_dir = os.path.join(output_dir, "routes")
        os.makedirs(routes_dir, exist_ok=True)
        
        lines = [
            "from faststream import FastStream",
            "from faststream.kafka import KafkaBroker",
            "from models import *",
            "import os",
            "",
            "broker = KafkaBroker('localhost:9092')",
            "stream_app = FastStream(broker)",
            ""
        ]

        # Bind a Kafka Consumer for every EntryPoint
        app_name = self.program.program_id.lower()
        for ep in self.program.procedure_division:
            func_name = ep.name.lower().replace("-", "_")
            in_topic = f"cobol.{app_name}.{func_name}.in"
            out_topic = f"cobol.{app_name}.{func_name}.out"
            
            lines.append(f"@broker.subscriber('{in_topic}')")
            lines.append(f"@broker.publisher('{out_topic}')")
            lines.append(f"async def process_{func_name}(payload: dict):")
            lines.append("    from runtime.shim import CobolRuntime")
            lines.append(f"    so_path = os.path.join(os.path.dirname(__file__), '..', 'runtime', '{self.program.program_id.lower()}.so')")
            lines.append("    try:")
            lines.append("        runtime = CobolRuntime(so_path)")
            lines.append(f"        return runtime.call('{ep.name}', payload=payload)")
            lines.append("    except Exception as e:")
            lines.append("        return {'error': str(e)}")
            lines.append("")

        output_path = os.path.join(routes_dir, "kafka_consumers.py")
        with open(output_path, "w") as f:
            f.write("\n".join(lines))
