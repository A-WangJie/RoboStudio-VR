"""Copy the local SDK's matched MuJoCo geometry/kinematics into the web app."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT.parent / '14-DOF robotic arm/S1_SDK_V2/src/S1_SDK/resource'


def numbers(element, key, default):
    return [float(v) for v in element.get(key, default).split()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource', type=Path, default=DEFAULT)
    args = parser.parse_args()
    source = args.resource.resolve()
    xml = source / 'gripper.xml'
    tree = ET.parse(xml).getroot()
    output = ROOT / 'app/assets/s1_v1'
    (output / 'meshes').mkdir(parents=True, exist_ok=True)
    assets = {}
    for mesh in tree.findall('asset/mesh'):
        path = source / 'meshes' / mesh.get('file')
        shutil.copy2(path, output / 'meshes' / path.name)
        assets[mesh.get('name')] = {'file': 'meshes/' + path.name,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def body(element):
        joints = element.findall('joint')
        if len(joints) > 1:
            raise ValueError('Only one joint per body is supported')
        node = {'name': element.get('name'),
                'position': numbers(element, 'pos', '0 0 0'),
                'quaternionWXYZ': numbers(element, 'quat', '1 0 0 0'),
                'visuals': [], 'children': [body(c) for c in element.findall('body')]}
        if joints:
            joint = joints[0]
            node['joint'] = {'name': joint.get('name'),
                'type': joint.get('type', 'hinge'),
                'axis': numbers(joint, 'axis', '0 0 1'),
                'position': numbers(joint, 'pos', '0 0 0'),
                'limits': numbers(joint, 'range', '0 0')}
        for geom in element.findall('geom'):
            if geom.get('type') != 'mesh':
                raise ValueError('Expected mesh geometry')
            node['visuals'].append({'mesh': geom.get('mesh'),
                'color': numbers(geom, 'rgba', '1 1 1 1'),
                'position': numbers(geom, 'pos', '0 0 0')})
        return node

    model = {'name': 'S1 V1', 'lengthUnit': 'm', 'angleUnit': 'rad',
        'source': 'S1_SDK_V2/resource/gripper.xml',
        'sourceSha256': hashlib.sha256(xml.read_bytes()).hexdigest(),
        'description': 'Local S1 V1 SDK simulation model; hardware geometry not independently calibrated.',
        'assets': assets, 'bodies': [body(b) for b in tree.findall('worldbody/body')],
        'armJoints': [f'{i}joint' for i in range(1, 7)],
        'gripperJoints': ['7joint', '8joint'],
        'homeRadians': [0, 0, 0, 0, 0, 0],
        'vrGrabRadians': [0.0, 0.8726646259971648, 1.1868238913561442, 0.9599310885968813, 0.0, 0.0],
        'gripperTravelMeters': 0.05,
        'tip': {'body': '6_Link', 'position': [0.1, 0, 0]}}
    shutil.copy2(xml, output / 'source.xml')
    (output / 'model.json').write_text(json.dumps(model, ensure_ascii=False, indent=2) + '\n')
    print(f'Imported {len(assets)} meshes into {output}')


if __name__ == '__main__':
    main()
