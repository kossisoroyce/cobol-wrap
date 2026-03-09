import os

from .ast import CobolProgram


class GraphQLEmitter:
    """ Generates a Strawberry GraphQL API representing the COBOL AST. """
    def __init__(self, program: CobolProgram, models_dict: dict):
        self.program = program
        self.models = models_dict

    def emit(self, output_dir: str):
        routes_dir = os.path.join(output_dir, "routes")
        os.makedirs(routes_dir, exist_ok=True)

        lines = [
            "import strawberry",
            "from typing import List, Optional",
            "from models import *",
            "from strawberry.fastapi import GraphQLRouter",
            "",
        ]

        # 1. Generate Strawberry Types from Pydantic Models
        # For simplicity, we decorate the generated Pydantic models directly if possible,
        # but Strawberry requires its own `@strawberry.type` classes usually.
        # We will emit wrapper types.
        for name, model in self.models.items():
            lines.append(f"@strawberry.experimental.pydantic.type(model={name}, all_fields=True)")
            lines.append(f"class {name}GQL:")
            lines.append("    pass\n")

        # 2. Generate Query and Mutation Root
        lines.append("@strawberry.type")
        lines.append("class Query:")
        lines.append("    @strawberry.field")
        lines.append("    def health(self) -> str:")
        lines.append("        return 'COBOL GraphQL Gateway API is running.'\n")

        lines.append("@strawberry.type")
        lines.append("class Mutation:")

        # Add Mutations for every EntryPoint
        for ep in self.program.procedure_division:
            req_name = f"{ep.name.replace('-', '').capitalize()}Request"
            res_name = f"{ep.name.replace('-', '').capitalize()}Response"
            func_name = ep.name.lower().replace("-", "_")

            lines.append("    @strawberry.mutation")
            lines.append(f"    def {func_name}(self, payload: strawberry.scalars.JSON) -> strawberry.scalars.JSON:")
            lines.append("        import os")
            lines.append("        from runtime.shim import CobolRuntime")
            lines.append(f"        so_path = os.path.join(os.path.dirname(__file__), '..', 'runtime', '{self.program.program_id.lower()}.so')")
            lines.append("        try:")
            lines.append("            runtime = CobolRuntime(so_path)")
            lines.append(f"            return runtime.call('{ep.name}', payload=payload)")
            lines.append("        except Exception as e:")
            lines.append("            return {'error': str(e)}")
            lines.append("")

        lines.append("schema = strawberry.Schema(query=Query, mutation=Mutation)")
        lines.append("graphql_app = GraphQLRouter(schema)")

        output_path = os.path.join(routes_dir, "graphql_api.py")
        with open(output_path, "w") as f:
            f.write("\n".join(lines))
