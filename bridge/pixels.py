"""Read a checksummed RGB strip; deliver data through existing LoD addon slots."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import re

COLUMNS = 128
SLOT_COUNT = 2048


def decode(image, cell=4.0):
    """Return session/id/slot/author/question; reject incomplete or corrupted frames."""
    pixels = image.load()
    result, accumulator, bits, length = bytearray(), 0, 0, None
    for index in range(10752):
        x = int((index % COLUMNS + 0.5) * cell)
        y = int((index // COLUMNS + 0.5) * cell)
        if x >= image.width or y >= image.height:
            return None
        rgb = pixels[x, y][:3]
        if any(48 < component < 207 for component in rgb):
            return None
        value = (int(rgb[0] >= 128) << 2) | (int(rgb[1] >= 128) << 1) | int(rgb[2] >= 128)
        accumulator = accumulator * 8 + value
        bits += 3
        if bits < 8:
            continue
        bits -= 8
        result.append((accumulator >> bits) & 255)
        accumulator &= (1 << bits) - 1
        if len(result) == 2 and result != b'\xc7\x1a':
            return None
        if len(result) == 4:
            length = int.from_bytes(result[2:4], 'big')
            if not 8 <= length <= 4000:
                return None
        if length is not None and len(result) == length + 6:
            a = b = 0
            for byte in result[2:-2]:
                a = (a + byte) % 255
                b = (b + a) % 255
            if result[-2:] != bytes((a, b)):
                return None
            try:
                fields = result[4:-2].decode('utf-8').split('\x1f', 8)
                context = ''
                if len(fields) in (8, 9):
                    session, request_id, slot, owner, author, owners, guests, question = fields[:8]
                    if len(fields) == 9 and author.casefold() == owner.casefold():
                        context = fields[8]
                    queue_info = {'owner': owner, 'owner_queued': int(owners), 'guest_queued': int(guests)}
                else:
                    session, request_id, slot, author, question = fields
                    queue_info = {'owner': author, 'owner_queued': 0, 'guest_queued': 0}
                if not re.fullmatch(r'\d+-\d+', session) or not request_id.isdigit():
                    return None
                slot = int(slot)
                if not 1 <= slot <= SLOT_COUNT or not author or not question:
                    return None
                return {'session': session, 'id': request_id, 'slot': slot,
                        'author': author, 'question': question, 'character_context': context, **queue_info}
            except (UnicodeError, ValueError):
                return None
    return None


def lua_string(text):
    # Decimal byte escapes cannot terminate a string or execute Lua from model text.
    return '"' + ''.join('\\%03d' % byte for byte in text.encode('utf-8')) + '"'


def settings_lua(settings):
    return 'WoWLLMChatSettings={share_replies=%s,allow_others=%s,guest_cooldown_seconds=%d,max_guest_queue=%d,share_character_context=%s,include_gold=%s,include_gearscore=%s,character_replies_private=%s}\n' % (
        'true' if settings.get('share_replies', True) else 'false',
        'true' if settings.get('allow_others', True) else 'false',
        int(settings.get('guest_cooldown_seconds', 300)), int(settings.get('max_guest_queue', 20)),
        'true' if settings.get('share_character_context', True) else 'false',
        'true' if settings.get('include_gold', False) else 'false',
        'true' if settings.get('include_gearscore', False) else 'false',
        'true' if settings.get('character_replies_private', True) else 'false')


def publish_settings(addons, settings):
    content = settings_lua(settings) + 'WoWLLMChatReply=nil\n'
    for slot in range(1, SLOT_COUNT + 1):
        path = Path(addons) / ('WoWLLMChat_S%04d' % slot) / 'Reply.lua'
        if not path.is_file():
            raise FileNotFoundError('Reply addons are missing. Run Setup before starting the bridge.')
        temporary = path.with_suffix('.tmp')
        temporary.write_text(content, encoding='ascii')
        temporary.replace(path)


def publish(addons, request, answer, error=False, settings=None, private=False):
    content = 'WoWLLMChatReply={session=%s,id=%s,text=%s,error=%s,private=%s}\n' % (
        lua_string(request['session']), lua_string(request['id']),
        lua_string(answer), 'true' if error else 'false', 'true' if private else 'false')
    if settings is not None:
        content = settings_lua(settings) + content
    # Cover a timer boundary; never modify addon manifests while the game runs.
    for slot in range(request['slot'], min(request['slot'] + 3, SLOT_COUNT + 1)):
        path = Path(addons) / ('WoWLLMChat_S%04d' % slot) / 'Reply.lua'
        if not path.is_file():
            raise FileNotFoundError('Reply files are missing. Close the game and run Install.ps1: ' + str(path))
        temporary = path.with_suffix('.tmp')
        temporary.write_text(content, encoding='ascii')
        temporary.replace(path)


class Capture:
    """Capture only a small corner of the foreground, configured game window."""
    def __init__(self, titles):
        if not hasattr(ctypes, 'windll'):
            raise RuntimeError('Screen capture requires Windows.')
        self.user32 = ctypes.windll.user32
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        try:
            # Physical screenshot coordinates on this worker only. The GUI sets
            # its process DPI mode before creating Tk, never from this thread.
            set_context = self.user32.SetThreadDpiAwarenessContext
            set_context.argtypes = [ctypes.c_void_p]
            set_context.restype = ctypes.c_void_p
            set_context(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
        self.titles = [title.casefold() for title in titles]
        self.cell = 4.0

    def read(self):
        from PIL import ImageGrab
        hwnd = self.user32.GetForegroundWindow()
        title = ctypes.create_unicode_buffer(512)
        self.user32.GetWindowTextW(hwnd, title, 512)
        if not any(candidate in title.value.casefold() for candidate in self.titles):
            return None
        rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
        if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)) or not self.user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            return None
        if rect.right < 300 or rect.bottom < 200:
            return None
        image = ImageGrab.grab(bbox=(origin.x, origin.y, origin.x+min(1536, rect.right),
                                    origin.y+min(900, rect.bottom)), all_screens=True)
        request = decode(image, self.cell)
        if request:
            return request
        # Accommodate UI scale / window sizing. Only a valid checksum is accepted.
        for step in range(12, 49):
            cell = step / 4
            if cell != self.cell:
                request = decode(image, cell)
                if request:
                    self.cell = cell
                    return request
        return None
