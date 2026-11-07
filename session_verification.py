"""Constant-size evidence about observed checks and subsequent edits."""

CHECKS = {'Pruebas y validación': 'Pruebas/validación', 'Compilación': 'Compilación'}
OUTCOMES = {'ok': 'informó éxito', 'error': 'informó un error', 'info': 'sin resultado conocido'}


class VerificationEvidence:
    def __init__(self):
        self.sequence = 0
        self.check = self.edit = None
        self.kind = self.outcome = None

    def observe(self, label, outcome, stamp):
        if label not in CHECKS and label != 'Edición de archivos':
            return
        self.sequence += 1
        order = (stamp.timestamp(), self.sequence)
        if label == 'Edición de archivos':
            if self.edit is None or order > self.edit:
                self.edit = order
        elif self.check is None or order > self.check:
            self.check = order
            self.kind = CHECKS[label]
            self.outcome = outcome if outcome in OUTCOMES else 'info'

    def summary(self):
        return {'check_at': self.check[0] if self.check else None,
                'check_kind': self.kind, 'check_outcome': self.outcome,
                'edit_at': self.edit[0] if self.edit else None,
                'edits_after_check': bool(self.edit and (self.check is None or self.edit > self.check))}


def verification_text(evidence, age=''):
    if not evidence:
        return ''
    if not evidence.get('check_at'):
        return 'Acciones de edición observadas; aún no se observó una comprobación.' if evidence.get('edit_at') else ''
    kind = evidence.get('check_kind')
    if kind not in CHECKS.values():
        return ''
    outcome = OUTCOMES.get(evidence.get('check_outcome'), OUTCOMES['info'])
    lines = [f'Última comprobación · {kind}: {outcome}' + (f' · hace {age}' if age else '')]
    if evidence.get('edits_after_check'):
        lines.append('Acciones de edición posteriores a esa comprobación.')
    return '\n'.join(lines)
