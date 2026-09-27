"""CSV machining inventories and the generated package README."""
import csv
import json

from .cad_helpers import meta
from . import output_formats
from .. import formats


def write_manifests(cfg,doc):
    ents=list(doc.modelspace());pmap={meta(e)['part_id']:meta(e) for e in ents if e.dxf.layer=='CUT_THROUGH'}
    def emit(name,rows):
        with (cfg.OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
            fields=list(rows[0]) if rows else ['part_id','feature_id','parent_pocket','center_u_mm','center_v_mm','radius_mm','depth_mm','intent','dxf_handle']
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    emit('parts_manifest.csv',[dict(part_id=pid,length_mm=d['length_mm'],width_mm=d['width_mm'],thickness_mm=cfg.THK,
         nest_x_mm=d['nesting_origin'][0],nest_y_mm=d['nesting_origin'][1],assembly_group=d['assembly_group'],
         A_face_in_assembly=d['assembly_face_A'],grain_axis='X',assembly_affine=json.dumps(d['assembly_map']),
         pocket_count=sum(meta(e).get('part_id')==pid and e.dxf.layer==cfg.POCKET_LAYER for e in ents)) for pid,d in pmap.items()])
    emit('pocket_manifest.csv',[dict(part_id=d['part_id'],feature_id=d['feature_id'],joint=d['joint'],pair_id=d['joint_id'],
         u0_mm=d['local_rect'][0],v0_mm=d['local_rect'][1],length_mm=d['local_rect'][2],width_mm=d['local_rect'][3],
         depth_mm=cfg.DEPTH,seat=d['seat'],mate_part_id=d['mate_part_id'],mate_feature_id=d['mate_feature_id'],
         open_edges=';'.join(d['open_edges']),A_face_in_assembly=pmap[d['part_id']]['assembly_face_A'],dxf_handle=e.dxf.handle)
         for e in ents if e.dxf.layer==cfg.POCKET_LAYER for d in [meta(e)]])
    emit('dogbone_manifest.csv',[dict(part_id=d['part_id'],feature_id=d['feature_id'],parent_pocket=d['parent_pocket'],
         center_u_mm=d['local_center'][0],center_v_mm=d['local_center'][1],radius_mm=cfg.R,depth_mm=cfg.DEPTH,
         intent='UNION_WITH_PARENT_POCKET',dxf_handle=e.dxf.handle)
         for e in ents if e.dxf.layer=='DOGBONE' for d in [meta(e)]])
    emit('hardware_reference_manifest.csv',[dict(hardware_id=d['hardware_id'],hardware_type=d['hardware_type'],part_id=d['part_id'],
         layer=e.dxf.layer,production_machining=False,front_face_position_only=True,depth_ref_mm=d.get('depth_ref_mm','UNSPECIFIED'),
         dxf_handle=e.dxf.handle) for e in ents if meta(e).get('kind')=='hardware_ref' and meta(e).get('view')=='nest' for d in [meta(e)]])


def write_readme(cfg,report):
    ma=report['manufacturing_assessment']
    lines=[f"한옥 창호 CAD 패키지 / {cfg.PARAMS['revision']}",f'형식: {cfg.TITLE}',
           f'외곽: {cfg.W:g} x {cfg.H:g} mm. 창짝 {cfg.NLEAF}개, 각각 {cfg.LW:g} x {cfg.LH:g} mm.',
           f"크기 기준: {'외경(완성 외곽)' if cfg.SIZE['basis']=='outer' else '내경(고정틀 안목)'} {cfg.SIZE['requested_mm'][0]:g} x {cfg.SIZE['requested_mm'][1]:g} mm 입력. 외경 {cfg.W:g} x {cfg.H:g}, 내경 {cfg.IW:g} x {cfg.IH:g} mm.",
           f'창짝당 창살: 세로 {cfg.NV}, 가로 {cfg.NH}. 교차점 {cfg.NV*cfg.NH}개.',
           f'부품 {cfg.NPART}, 홈 {cfg.NPOCKT}, 도그본 {cfg.NDOG}, 결합쌍 {cfg.NPOCKT//2}.',
           f'원판: {cfg.BL:g} x {cfg.BWD:g} x {cfg.THK:g} mm. 부재 길이는 목리 X 방향.',
           f'가공 깊이: {cfg.DEPTH:g} mm. 모든 가공은 A면. 공구 지름 {cfg.PARAMS["machining"]["tool_diameter"]:g}, 도그본 R{cfg.R:g}.',
           f'창짝-고정틀 간극 {cfg.GAP_OUT:g} mm.'+(f' 창짝 사이 간극 {cfg.GAP_MID:g} mm.' if cfg.NLEAF==2 else ''),
           f'그림: {cfg.A3W:g} x {cfg.A3H:g} mm, 후면 기준영역 안에 중앙 배치, 각 변 최소 여유 {cfg.PMG:g} mm.' if cfg.PICTURE else
           f'화판: {cfg.ARTW:g} x {cfg.ARTH:g} x {cfg.ARTT:g} mm. 고정틀이 각 변 {cfg.ACOV:g} mm를 덮습니다.' if cfg.ART else '그림: 지정하지 않음.',
           *([f'뒤틀(B01·B02) 4개: 폭 {cfg.BMW:g} mm, 안쪽 {cfg.D["back_inner_w"]:g} x {cfg.D["back_inner_h"]:g} mm, 끼움 여유 {cfg.AFIT:g} mm, 맞댄 이음.',
              f'층: 고정틀·창짝·창살은 Z 0~{cfg.THK:g} mm, 뒤틀은 Z {-cfg.THK:g}~0 mm. 그 안에 스페이서 {cfg.ASPC:g} mm와 화판 {cfg.ARTT:g} mm가 들어갑니다.',
              '스페이서·뒷판·걸이 철물은 별도 조달이며 PENDING입니다. 뒤틀 모서리 맞댄 이음의 접착·고정 방법도 확인해야 합니다.'] if cfg.ART else []),
           '실제 존재하는 결합 상세: '+', '.join(formats.detail_variants(cfg.PARAMS)),
           f'경첩 {2*cfg.NLEAF}, 손잡이 {cfg.NLEAF}, 캐치 {cfg.NLEAF}: 실물 선정 전 참고 위치.',
           '경첩 부재: '+', '.join(f'{f.hinge_stile}/{f.fixed_stile}' for f in cfg.FORMAT),
           '손잡이 부재: '+', '.join(f.handle_stile for f in cfg.FORMAT),
           '',f"저장 DXF 재검증: {report['checks_passed']}개 검사 PASS. 검사 ID·기대값·실측값·허용 오차는 validation_report.json.",
           f"실측 최소 홈 사이 폭: {ma['machined_web']['measured_mm']}; 가장자리 폭: {ma['edge_web']['measured_mm']}; 잔존 두께: {ma['remaining_thickness']['measured_mm']} mm.",
           '제작용 최소값은 미확정(null/PENDING). 명목 기하 합격은 제작 승인이나 강도 보증이 아닙니다.',
           '부재는 명목 무공차입니다. 시험편·끼움 공차·재료·하드웨어·후판 고정·개폐 간섭·CAM·고정 지그를 확인해야 합니다.',
           'CUT_THROUGH는 전체 두께. POCKET과 DOGBONE은 부모 홈과 합쳐 절삭합니다. 개방 경계는 폐기물 방향 오버런이 필요합니다.',
           'HINGE_REF와 LATCH_REF는 생산 가공에서 제외합니다. 공구 경로·탭·이송·회전수·G-code는 포함하지 않습니다.',
           '', '파일: '+', '.join(('window.dxf',*output_formats.filenames()))+', PNG 5장, CSV 4종, design_request.json, design_parameters.json, design_spec.json,',
           'resolved_parameters.json, validation_report.json, environment.json, package_manifest.json, source/.',
           '재생성: source/requirements.txt를 설치하고 PYTHONPATH=source python -m hanok_generator build --input design_request.json --output rebuilt',
           '검증: PYTHONPATH=source python -m hanok_generator verify .',
           'DXF는 고정 해시 시드와 메타데이터를 사용합니다. PNG 재현에는 environment.json의 폰트와 라이브러리도 같아야 합니다.',
           '파일을 수정한 뒤 기존 매니페스트를 덮어쓰지 마십시오. 새 입력으로 새 패키지를 생성하십시오.']
    (cfg.OUT/'README.txt').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
