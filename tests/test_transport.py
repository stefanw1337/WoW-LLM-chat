from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'bridge'))
sys.path.insert(0, str(ROOT / '.testdeps'))
from pixels import decode, publish, publish_settings, lua_string
from lupa.lua51 import LuaRuntime

MOCK = r'''
frames={}; messages={}; joined=false; loaded={}; sent={}; fakeNow=1234567890
local methods={}
function methods:SetFrameStrata() end
function methods:SetFrameLevel() end
function methods:SetPoint(_,_,_,x,y) self.x=x; self.y=y end
function methods:SetWidth() end
function methods:SetHeight() end
function methods:SetScale() end
function methods:GetEffectiveScale() return 1 end
function methods:Show() self.visible=true end
function methods:Hide() self.visible=false end
function methods:SetTexture(r,g,b,a) self.rgb={r,g,b} end
function methods:RegisterEvent() end
function methods:SetScript(name,fn) self[name]=fn end
function methods:CreateTexture()
    local t=setmetatable({}, {__index=methods})
    self.textures=self.textures or {}; table.insert(self.textures,t); return t
end
function CreateFrame(_,name)
    local f=setmetatable({name=name},{__index=methods}); table.insert(frames,f); return f
end
UIParent=CreateFrame('Frame')
ChatTypeInfo={CHANNEL7={r=0.9,g=0.7,b=0.65},CHANNEL={r=1,g=0.75,b=0.75}}
DEFAULT_CHAT_FRAME={AddMessage=function(self,text,r,g,b) table.insert(messages,text); lastColor={r,g,b} end}
function GetCVar() return '1920x1080' end
function GetChannelName() return joined and 7 or 0 end
function JoinChannelByName(name) joined=true end
function ChatFrame_AddChannel() end
function UnitName() return 'TestPlayer' end
function time() return fakeNow end
function SendChatMessage(text,kind,language,target) table.insert(sent,{text=text,kind=kind,target=target}) end
function ChatFrame_AddMessageEventFilter(event,fn) echoFilter=fn end
function LoadAddOn(name) loaded[#loaded+1]=name; if replySource then assert(loadstring(replySource))() end; return true end
SlashCmdList={}
'''


class TransportTests(unittest.TestCase):
    def test_sensitive_fields_opt_in_only(self):
        self.lua.execute('moneyCalls=0; scoreCalls=0; function GetMoney() moneyCalls=moneyCalls+1; return 123456 end; function GearScore_GetScore() scoreCalls=scoreCalls+1; return 4567 end')
        default=self.lua.eval('WoWLLMCharacterSnapshot()')
        self.assertNotIn('Gold:',default)
        self.assertNotIn('GearScore:',default)
        self.assertEqual(self.lua.globals().moneyCalls,0)
        self.assertEqual(self.lua.globals().scoreCalls,0)
        enabled=self.lua.eval('WoWLLMCharacterSnapshot({include_gold=true,include_gearscore=true})')
        self.assertIn('Gold: 12g 34s 56c',enabled)
        self.assertIn('GearScore: 4567',enabled)
        self.lua.execute('GearScore_GetScore=nil')
        self.assertIn('GearScore: unavailable',self.lua.eval('WoWLLMCharacterSnapshot({include_gearscore=true})'))

    def test_private_character_reply_not_broadcast_but_guest_is(self):
        self.request('My build?')
        self.finish()
        self.lua.execute('frames[2]:OnUpdate(2)')
        self.assertEqual(len(self.lua.globals().sent),0)
        self.request('Hello','Guest')
        self.finish()
        self.assertEqual(len(self.lua.globals().sent),1)
        self.assertEqual(self.lua.globals().sent[1].kind,'CHANNEL')

    def test_private_flag_survives_setting_change(self):
        self.lua.execute('WoWLLMChatDB.settings.character_replies_private=false')
        self.request()
        request=decode(self.screenshot())
        with tempfile.TemporaryDirectory() as folder:
            for slot in range(1,4):
                p=Path(folder)/('WoWLLMChat_S%04d'%slot)
                p.mkdir(); (p/'Reply.lua').write_text('')
            publish(folder,request,'Private gold answer',private=True)
            self.lua.globals().replySource=(Path(folder)/'WoWLLMChat_S0001/Reply.lua').read_text()
            self.lua.execute('frames[2]:OnUpdate(6)')
        self.assertEqual(len(self.lua.globals().sent),0)

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.lua.execute((ROOT / 'Addon/WoWLLMChat/Character.lua').read_text(encoding='utf-8'))
        self.lua.execute((ROOT / 'Addon/WoWLLMChat/WoWLLMChat.lua').read_text(encoding="utf-8"))
        self.lua.execute("frames[2]:OnEvent('PLAYER_ENTERING_WORLD'); frames[2]:OnUpdate(6)")

    def request(self, text='How do I bake a chocolate cake?', author='TestPlayer'):
        self.lua.globals().question = text
        self.lua.globals().author = author
        self.lua.execute("frames[2]:OnEvent('CHAT_MSG_CHANNEL',question,author,'','','','',0,7,'AI')")

    def finish(self, text='A short answer.'):
        request = decode(self.screenshot())
        self.lua.globals().replySource = 'WoWLLMChatReply={session=%s,id=%s,text=%s}' % (
            lua_string(request['session']),lua_string(request['id']),lua_string(text))
        self.lua.execute('frames[2]:OnUpdate(6)')

    def screenshot(self):
        result = Image.new('RGB', (512, 336))
        draw = ImageDraw.Draw(result)
        textures = self.lua.globals().frames[3].textures
        for t in textures.values():
            if t.visible:
                x, y = int(t.x), int(-t.y)
                rgb = tuple(int(t.rgb[i] * 255) for i in range(1,4))
                draw.rectangle((x,y,x+3,y+3), fill=rgb)
        return result

    def test_lua51_pixels_to_python_to_lua_chat(self):
        self.request('How do I bake a café-style blueberry cake?')
        request = decode(self.screenshot())
        self.assertEqual(request['question'], 'How do I bake a café-style blueberry cake?')
        self.assertEqual(request['slot'], 1)
        with tempfile.TemporaryDirectory() as folder:
            for slot in range(1,4):
                p = Path(folder) / ('WoWLLMChat_S%04d' % slot)
                p.mkdir(); (p/'Reply.lua').write_text('')
            answer = 'Use flour and blueberries for a café-style cake. "quoted"; os.execute("NO")'
            publish(folder, request, answer)
            self.lua.globals().replySource = (Path(folder)/'WoWLLMChat_S0001/Reply.lua').read_text()
            self.lua.execute('frames[2]:OnUpdate(6)')
            shown = list(self.lua.globals().messages.values())[-1]
            self.assertIn('[7. AI] [|cff66ccffQwen3 (MoE)|r]: ', shown)
            self.assertEqual(tuple(self.lua.globals().lastColor.values()), (0.9,0.7,0.65))
            self.assertIn(answer, shown)
            self.assertFalse(self.lua.globals().frames[3].visible)

    def test_corrupt_pixel_rejected(self):
        self.request()
        image = self.screenshot()
        image.putpixel((2,2),(127,127,127))
        self.assertIsNone(decode(image))

    def test_long_reply_becomes_bounded_utf8_chat_entries(self):
        self.request()
        request = decode(self.screenshot())
        answer = ('A long caf\u00e9 reply with Unicode \u4f60\u597d. ' * 40).strip()
        self.lua.globals().replySource = 'WoWLLMChatReply={session=%s,id=%s,text=%s}' % (
            lua_string(request['session']), lua_string(request['id']), lua_string(answer))
        self.lua.execute('frames[2]:OnUpdate(6)')
        prefix='[7. AI] [|cff66ccffQwen3 (MoE)|r]: '
        entries=[m for m in self.lua.globals().messages.values() if m.startswith(prefix)]
        self.assertGreater(len(entries), 1)
        self.assertTrue(all(len(m.encode('utf-8')) <= 255 for m in entries))
        reconstructed=''.join(m[len(prefix):] for m in entries)
        self.assertEqual(reconstructed, answer)

    def test_stale_reply_rejected_and_slot_advances(self):
        self.request()
        self.lua.globals().replySource = 'WoWLLMChatReply={session="old",id="1",text="STALE"}'
        self.lua.execute('frames[2]:OnUpdate(6)')
        self.assertEqual(decode(self.screenshot())['slot'], 2)
        self.assertNotIn('STALE', '\n'.join(self.lua.globals().messages.values()))

    def test_other_players_ignored_and_cancel(self):
        self.lua.execute('WoWLLMChatDB.settings.allow_others=false')
        self.lua.execute("frames[2]:OnEvent('CHAT_MSG_CHANNEL','hello','Other','','','','',0,7,'AI')")
        self.assertFalse(self.lua.globals().frames[3].visible)
        self.request()
        self.lua.execute("SlashCmdList.WOWLLMCHAT('cancel')")
        self.assertFalse(self.lua.globals().frames[3].visible)

    def test_lua_escaping(self):
        value = '\\"\nreturn os.execute("unsafe") -- æøå'
        self.assertEqual(self.lua.eval(lua_string(value)), value)

    def test_owner_priority_and_fifo_without_interrupting_active_guest(self):
        self.request('First guest', 'GuestOne')
        self.request('Second guest', 'GuestTwo')
        self.request('Owner first')
        self.request('Owner second')
        active = decode(self.screenshot())
        self.assertEqual(active['author'], 'GuestOne')
        self.assertEqual((active['owner_queued'],active['guest_queued']), (2,1))
        self.finish()
        self.assertEqual(decode(self.screenshot())['question'], 'Owner first')
        self.finish()
        self.assertEqual(decode(self.screenshot())['question'], 'Owner second')
        self.finish()
        self.assertEqual(decode(self.screenshot())['author'], 'GuestTwo')

    def test_guest_cooldown_owner_exempt_and_live_settings(self):
        self.request('Guest question','Guest')
        self.finish()
        self.request('Too soon','Guest')
        self.assertFalse(self.lua.globals().frames[3].visible)
        self.assertTrue(any('300 seconds' in e.text for e in self.lua.globals().sent.values()))
        self.request('Owner exempt')
        self.finish()
        self.lua.globals().replySource = 'WoWLLMChatSettings={guest_cooldown_seconds=60}'
        self.lua.execute('fakeNow=fakeNow+60; frames[2]:OnUpdate(30)')
        self.request('Allowed now','Guest')
        self.assertEqual(decode(self.screenshot())['question'], 'Allowed now')

    def test_guest_queue_limit_reserves_room_for_owner(self):
        self.lua.execute('WoWLLMChatDB.settings.max_guest_queue=1')
        self.request('Active','GuestOne')
        self.request('Waiting','GuestTwo')
        self.request('Rejected','GuestThree')
        self.request('Owner still accepted')
        request = decode(self.screenshot())
        self.assertEqual((request['owner_queued'],request['guest_queued']), (1,1))
        self.assertTrue(any('queue is full' in e.text for e in self.lua.globals().sent.values()))

    def test_public_reply_rate_limit_and_no_feedback_loop(self):
        self.lua.execute('WoWLLMChatDB.settings.character_replies_private=false')
        self.request()
        self.finish('Long answer. ' * 60)
        broadcasts=[e for e in self.lua.globals().sent.values() if e.kind=='CHANNEL']
        self.assertEqual(len(broadcasts),1)
        self.assertLessEqual(len(broadcasts[0].text.encode()),255)
        self.assertIn('-> TestPlayer',broadcasts[0].text)
        self.request(broadcasts[0].text)
        self.assertFalse(self.lua.globals().frames[3].visible)
        self.lua.execute('frames[2]:OnUpdate(0.1)')
        self.assertEqual(len(self.lua.globals().sent),1)
        self.lua.execute('frames[2]:OnUpdate(1.5)')
        self.assertEqual(len(self.lua.globals().sent),2)
        self.assertTrue(self.lua.globals().echoFilter(None,'CHAT_MSG_CHANNEL',broadcasts[0].text,'TestPlayer'))

    def test_switching_to_private_clears_broadcasts_and_guest_backlog(self):
        self.request('Owner question')
        self.request('Guest queued','Guest')
        self.lua.globals().replySource='WoWLLMChatSettings={share_replies=false,allow_others=false}'
        self.lua.execute('frames[2]:OnUpdate(6)')
        self.assertEqual(decode(self.screenshot())['guest_queued'],0)
        self.finish()
        self.assertEqual(len(self.lua.globals().sent),0)

    def test_settings_file_sync_and_reply_preserve_policy(self):
        self.request()
        request=decode(self.screenshot())
        policy=dict(share_replies=False,allow_others=False,guest_cooldown_seconds=90,max_guest_queue=3)
        with tempfile.TemporaryDirectory() as folder:
            for i in range(1,4):
                path=Path(folder)/('WoWLLMChat_S%04d'%i)
                path.mkdir(); (path/'Reply.lua').write_text('')
            with patch('pixels.SLOT_COUNT',3):
                publish_settings(folder,policy)
                publish(folder,request,'Private answer',settings=policy)
            self.lua.globals().replySource=(Path(folder)/'WoWLLMChat_S0001/Reply.lua').read_text()
            self.lua.execute('frames[2]:OnUpdate(6)')
            self.assertFalse(self.lua.globals().WoWLLMChatDB.settings.share_replies)
            self.assertEqual(self.lua.globals().WoWLLMChatDB.settings.guest_cooldown_seconds,90)
            self.assertEqual(len(self.lua.globals().sent),0)

    def test_character_snapshot_owner_only_refreshes_and_can_be_disabled(self):
        self.lua.execute('''
            characterLevel=80
            function UnitLevel() return characterLevel end
            function UnitClass() return 'Mage','MAGE' end
            function GetRealmName() return 'CustomRealm' end
            function GetInventoryItemLink(unit,slot)
                if slot==16 then return '|cffa335ee|Hitem:12345:0:0:0|h[Test Staff]|h|r' end
            end
            function GetNumTalentTabs() return 1 end
            function GetTalentTabInfo() return 'Frost',nil,51 end
            function GetNumTalents() return 1 end
            function GetTalentInfo() return 'Ice Barrier',nil,7,1,1,1 end
            function GetNumQuestLogEntries() return 2 end
            function GetQuestLogTitle(i)
                if i==1 then return 'Zone header',0,nil,0,true end
                return 'Test Quest',80,nil,0,false,false,1,false,987
            end
        ''')
        self.request('Suggest a build')
        context=decode(self.screenshot())['character_context']
        for value in ['level=80','class=Mage','CustomRealm','Test Staff','itemID=12345','Ice Barrier 1/1','Test Quest','id=987']:
            self.assertIn(value,context)
        self.assertNotIn('Zone header',context)
        self.finish()
        self.request('My build?', 'Guest')
        self.assertEqual(decode(self.screenshot())['character_context'],'')
        self.finish()
        self.lua.execute('characterLevel=81')
        self.request('Updated build?')
        self.assertIn('level=81',decode(self.screenshot())['character_context'])
        self.finish()
        self.lua.execute('WoWLLMChatDB.settings.share_character_context=false')
        self.request('Just chat')
        self.assertEqual(decode(self.screenshot())['character_context'],'')

    def test_large_unicode_snapshot_fits_pixel_transport(self):
        self.lua.execute('''
            function GetInventoryItemLink(unit,slot) return '|Hitem:12345:0|h[' .. string.rep('Long name ',30) .. ']|h' end
            function GetNumTalentTabs() return 3 end
            function GetNumTalents() return 100 end
            function GetTalentInfo() return 'Long talent name',nil,1,1,3,3 end
        ''')
        self.request('x'*1000)
        request=decode(self.screenshot())
        self.assertIsNotNone(request)
        self.assertLessEqual(len(request['character_context'].encode()),2700)
        self.assertIn('Partial snapshot',request['character_context'])


if __name__ == '__main__':
    unittest.main()
