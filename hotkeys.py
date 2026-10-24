"""Explorer-only shortcuts with exact modifier matching."""
from dataclasses import dataclass

KEY_CODES = {**{f'F{i}':111+i for i in range(1,25)},
             **{chr(i):i for i in range(65,91)}, **{str(i):48+i for i in range(10)},
             'Space':32,'Insert':45,'Home':36,'End':35,'PageUp':33,'PageDown':34,
             'Pause':19,'ScrollLock':145}
MODIFIERS = ('Ctrl','Alt','Shift')
MOD_CODES = {'Ctrl':17,'Alt':18,'Shift':16,'WinLeft':91,'WinRight':92}
ALIASES = {'CONTROL':'Ctrl','CTRL':'Ctrl','ALT':'Alt','SHIFT':'Shift',
           'SPACE':'Space','INSERT':'Insert','HOME':'Home','END':'End',
           'PAGEUP':'PageUp','PAGEDOWN':'PageDown','PRIOR':'PageUp','NEXT':'PageDown',
           'PAUSE':'Pause','SCROLLLOCK':'ScrollLock','SCROLL_LOCK':'ScrollLock'}
RESERVED = {'Alt+F4','Alt+Space','Ctrl+C','Ctrl+V','Ctrl+X','Ctrl+A','Ctrl+Z','Ctrl+Y',
            'Ctrl+F','Ctrl+L','Ctrl+N','Ctrl+W','Ctrl+R','Ctrl+Shift+N','Ctrl+Shift+Esc'}


@dataclass(frozen=True)
class Hotkey:
    name: str
    vk: int
    modifiers: frozenset

    def matches(self,vk,pressed):
        return self.vk==vk and self.modifiers==frozenset(pressed)


def parse_hotkey(value):
    if not isinstance(value,str) or len(value)>64:
        raise ValueError('단축키를 선택하거나 눌러서 지정해 주세요.')
    parts=[ALIASES.get(p.strip().upper(),p.strip().upper()) for p in value.split('+')]
    if not parts or any(not p for p in parts) or len(set(parts))!=len(parts):
        raise ValueError('단축키 형식을 확인해 주세요. 예: F12, Ctrl+Shift+P')
    keys=[p for p in parts if p not in MODIFIERS]
    if len(keys)!=1 or keys[0] not in KEY_CODES:
        raise ValueError('F1~F24, 영문·숫자, Space·Insert·Home·End·PageUp·PageDown을 사용할 수 있어요.')
    modifiers=frozenset(p for p in parts if p in MODIFIERS)
    name='+'.join([m for m in MODIFIERS if m in modifiers]+keys)
    if name in RESERVED:
        raise ValueError('복사·붙여넣기·창 닫기 등 기본 기능에 쓰는 조합이에요. 다른 단축키를 선택해 주세요.')
    return Hotkey(name,KEY_CODES[keys[0]],modifiers)


def event_hotkey(event):
    vk=event.keycode
    key=next((k for k,v in KEY_CODES.items() if v==vk),None)
    if not key:
        return None
    parts=[]
    if event.state & 4:parts.append('Ctrl')
    # Windows Tk uses 0x20000 for Alt; bit 8 can be the Num Lock toggle.
    if event.state & 0x20000:parts.append('Alt')
    if event.state & 1:parts.append('Shift')
    return parse_hotkey('+'.join(parts+[key])).name
