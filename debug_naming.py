from formkit_ninja.formkit_schema import FormKitNode
from formkit_ninja.parser.type_convert import NodePath

node1 = FormKitNode.parse_obj({"$formkit": "group", "name": "TF_6_1_1"}).__root__
node2 = FormKitNode.parse_obj({"$formkit": "group", "name": "meetingInformation"}).__root__

path = NodePath(node1) / node2
print(f"Nodes: {[getattr(n, 'name') for n in path.nodes]}")
print(f"Class name: {path.classname}")
