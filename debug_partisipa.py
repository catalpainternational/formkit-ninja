from tests.parser.partisipanodepath_rewritten import PartisipaNodePathRewritten


class MockNode:
    name = "latitude"
    formkit = "text"


node = MockNode()
path = PartisipaNodePathRewritten(node)

print(f"Pydantic type: {path.to_pydantic_type()}")
print(f"Django type: {path.to_django_type()}")
print(f"Django args extra: {path.get_django_args_extra()}")
print(f"Django args: {path.to_django_args()}")
