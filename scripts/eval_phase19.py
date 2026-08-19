import asyncio
from app.agents.project_import_extraction import GeminiProjectImportExtractor
from app.config.settings import Settings


async def run_eval():
    settings = Settings(use_fake_model=False)

    extractor = GeminiProjectImportExtractor(settings)

    source_text1 = "Plastering requires 100 bags of cement."

    print(f"Extracting: {source_text1}")
    result1 = await extractor.extract(source_text1)
    print("Materials:", result1.materials)
    print("Requirements:", result1.material_requirements)

    source_text2 = "Foundation due on the 19th."
    print(f"\nExtracting: {source_text2}")
    result2 = await extractor.extract(source_text2)
    print("Tasks:", result2.tasks)
    print("Warnings:", getattr(result2, "warnings", "No warnings field"))


if __name__ == "__main__":
    asyncio.run(run_eval())
