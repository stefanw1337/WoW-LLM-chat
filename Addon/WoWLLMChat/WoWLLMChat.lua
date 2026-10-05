-- Pixels out; load-on-demand replies in. Legacy and modern client APIs.
local LoadAddOn = (C_AddOns and C_AddOns.LoadAddOn) or LoadAddOn
local GetCVar = (C_CVar and C_CVar.GetCVar) or GetCVar
local SendChat = (C_ChatInfo and C_ChatInfo.SendChatMessage) or SendChatMessage
local function readable(value) return not (issecretvalue and issecretvalue(value)) end
local function chatLocked()
    return C_ChatInfo and C_ChatInfo.InChatMessagingLockdown and C_ChatInfo.InChatMessagingLockdown()
end
local function send(text,kind,language,target)
    if chatLocked() or not SendChat then return false end
    return pcall(SendChat,text,kind,language,target)
end
local CHANNEL, SLOT_COUNT, CELL, COLUMNS = "AI", 2048, 4, 128
local frame = CreateFrame("Frame")
local strip = CreateFrame("Frame", "WoWLLMPixelStrip", UIParent)
strip:SetFrameStrata("TOOLTIP")
strip:SetFrameLevel(10000)
strip:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
strip:SetWidth(CELL*COLUMNS); strip:SetHeight(CELL*84); strip:Hide()
local textures, pending, backlog, outgoing = {}, nil, {}, {}
WoWLLMChatDB=WoWLLMChatDB or {}
local db=WoWLLMChatDB
db.lastAccepted=db.lastAccepted or {}
db.settings=db.settings or {share_replies=true,allow_others=true,guest_cooldown_seconds=300,max_guest_queue=20}
local settings=db.settings
local notices={}
local sendTime=0
local function isOwner(author)
    if not readable(author) or type(author)~="string" then return false end
    local name,realm=UnitName("player")
    name=name or ""
    if string.lower(author)==string.lower(name) then return true end
    realm=realm or (GetNormalizedRealmName and GetNormalizedRealmName()) or (GetRealmName and GetRealmName()) or ""
    return string.lower(author)==string.lower(name .. "-" .. realm:gsub("%s+",""))
end
local function counts()
    local owners,guests=0,0
    for _,entry in ipairs(backlog) do
        if isOwner(entry.author) then owners=owners+1 else guests=guests+1 end
    end
    return owners,guests
end
local function applySettings(data)
    if type(data)~="table" then return end
    for _,key in ipairs({"include_gold","include_gearscore","character_replies_private"}) do
        if type(data[key])=="boolean" then settings[key]=data[key] end
    end
    if type(data.share_replies)=="boolean" then settings.share_replies=data.share_replies end
    if type(data.allow_others)=="boolean" then settings.allow_others=data.allow_others end
    if type(data.share_character_context)=="boolean" then settings.share_character_context=data.share_character_context end
    if type(data.guest_cooldown_seconds)=="number" then settings.guest_cooldown_seconds=math.max(0,math.min(3600,data.guest_cooldown_seconds)) end
    if type(data.max_guest_queue)=="number" then settings.max_guest_queue=math.max(1,math.min(100,math.floor(data.max_guest_queue))) end
    if not settings.share_replies then outgoing={} end
    if not settings.share_replies or not settings.allow_others then
        local keep={}
        for _,entry in ipairs(backlog) do if isOwner(entry.author) then keep[#keep+1]=entry end end
        backlog=keep
    end
end
local function tell(author,text)
    local key=string.lower(author)
    if time()-(notices[key] or 0)<30 then return end
    notices[key]=time()
    send("[Qwen3 (MoE)] " .. text,"WHISPER",nil,author)
end
local session = tostring(time()) .. "-" .. tostring(math.random(100000,999999))
local sequence, nextSlot, joinTime, pollTime, scaleTime = 0,1,5,0,0
local function info(text) DEFAULT_CHAT_FRAME:AddMessage("|cff66ccffWoWLLM:|r " .. text) end
local function join()
    if GetChannelName(CHANNEL)==0 then JoinChannelByName(CHANNEL) end
    if GetChannelName(CHANNEL)>0 then ChatFrame_AddChannel(DEFAULT_CHAT_FRAME,CHANNEL) end
end
local function draw()
    if not pending then strip:Hide(); return end
    local owners,guests=counts()
    local context=(isOwner(pending.author) and settings.share_character_context~=false) and (pending.context or "") or ""
    local payload=table.concat({session,pending.id,tostring(nextSlot),UnitName("player"),pending.author,tostring(owners),tostring(guests),pending.text,context},"\31")
    local bytes={199,26,math.floor(#payload/256),#payload%256}
    for i=1,#payload do bytes[#bytes+1]=payload:byte(i) end
    local a,b=0,0
    for i=3,#bytes do a=(a+bytes[i])%255; b=(b+a)%255 end
    bytes[#bytes+1]=a; bytes[#bytes+1]=b
    local cells,acc,bits={},0,0
    for _,byte in ipairs(bytes) do
        acc=acc*256+byte; bits=bits+8
        while bits>=3 do
            bits=bits-3; cells[#cells+1]=math.floor(acc/2^bits)%8; acc=acc%2^bits
        end
    end
    if bits>0 then cells[#cells+1]=acc*2^(3-bits) end
    for i,v in ipairs(cells) do
        local t=textures[i]
        if not t then
            t=strip:CreateTexture(nil,"OVERLAY")
            t:SetWidth(CELL); t:SetHeight(CELL)
            t:SetPoint("TOPLEFT",strip,"TOPLEFT",((i-1)%COLUMNS)*CELL,-math.floor((i-1)/COLUMNS)*CELL)
            textures[i]=t
        end
        local setColor=t.SetColorTexture or t.SetTexture
        setColor(t,math.floor(v/4)%2,math.floor(v/2)%2,v%2,1); t:Show()
    end
    for i=#cells+1,#textures do textures[i]:Hide() end
    strip:Show()
end
local function beginNext()
    local index=1
    for i,entry in ipairs(backlog) do if isOwner(entry.author) then index=i; break end end
    pending=table.remove(backlog,index); pollTime=0
    if pending and isOwner(pending.author) and settings.share_character_context~=false and WoWLLMCharacterSnapshot then
        local ok,context=pcall(WoWLLMCharacterSnapshot,settings)
        pending.context=ok and context or "Character snapshot unavailable: client restricted or unsupported data."
    end
    draw()
end
local function display(text,isError,author,forcePrivate)
    text=tostring(text or ""):gsub("|","/"):gsub("[%z\1-\31\127]"," ")
    local label=isError and "Bridge status" or "Qwen3 (MoE)"
    if author and not isOwner(author) then label=label .. " -> " .. author end
    local channel=GetChannelName(CHANNEL)
    local color=ChatTypeInfo["CHANNEL" .. channel] or ChatTypeInfo.CHANNEL
    local prefix="[" .. channel .. ". AI] [|cff66ccff" .. label .. "|r]: "
    -- A giant AddMessage can overflow the old scrolling frame vertically.
    -- Keep each entry below 255 bytes, including the prefix and color escapes.
    local networkPrefix="[Qwen3 (MoE) -> " .. (author or UnitName("player")) .. "]: "
    local share=settings.share_replies and not isError and not forcePrivate
    local limit=math.min(255-#prefix,255-#networkPrefix)
    while #text>0 do
        local cut=math.min(limit,#text)
        if cut<#text then
            -- Never split a UTF-8 code point between messages.
            while cut>0 and text:byte(cut+1)>=128 and text:byte(cut+1)<192 do cut=cut-1 end
            local space=text:sub(1,cut):match("^.*() ")
            if space and space>cut/2 then cut=space end
        end
        local piece=text:sub(1,cut)
        DEFAULT_CHAT_FRAME:AddMessage(prefix .. piece,color.r,color.g,color.b)
        if share then outgoing[#outgoing+1]=networkPrefix .. piece end
        text=text:sub(cut+1):gsub("^%s+", "")
    end
end
local function poll()
    -- Modern clients may prohibit loading addons while in combat.
    if InCombatLockdown and InCombatLockdown() then return end
    if nextSlot>SLOT_COUNT then
        info("No reply slots remain. Log out and back in when convenient. The addon will not reload automatically.")
        pending=nil; backlog={}; strip:Hide(); return
    end
    WoWLLMChatReply=nil; WoWLLMChatSettings=nil
    local ok,loaded,reason=pcall(LoadAddOn,string.format("WoWLLMChat_S%04d",nextSlot))
    if not ok then return end
    if not loaded then
        if reason=="MISSING" or reason=="DISABLED" then
            info("Reply addons are missing or disabled. Close the game and run Install.ps1.")
            pending=nil; backlog={}; strip:Hide()
        end
        return
    end
    nextSlot=nextSlot+1
    applySettings(WoWLLMChatSettings)
    local reply=WoWLLMChatReply
    if pending and type(reply)=="table" and reply.session==session and reply.id==pending.id then
        display(reply.text,reply.error,pending.author,reply.private or (isOwner(pending.author) and pending.context and settings.character_replies_private~=false))
        if reply.error and not isOwner(pending.author) then tell(pending.author,"The AI server is unavailable or returned an error. Please try again later.") end
        beginNext()
    else draw() end
end
frame:RegisterEvent("PLAYER_ENTERING_WORLD"); frame:RegisterEvent("CHAT_MSG_CHANNEL")
frame:SetScript("OnEvent",function(self,event,...)
    if event=="PLAYER_ENTERING_WORLD" then
        joinTime=5; info("Joining the AI channel. Start LM Studio and Start-Bridge.cmd. Use /wllm status for details."); return
    end
    local message,author,_,_,_,_,_,_,channelName=...
    if chatLocked() or not readable(message) or not readable(author) or not readable(channelName) then return end
    if type(message)~="string" or type(author)~="string" then return end
    if string.lower(channelName or "")~=string.lower(CHANNEL) then return end
    -- Ignore every AI-labelled message, including our public reply echoes.
    if message:match("^%[Qwen3 %(MoE%)") then return end
    local owner=isOwner(author)
    if owner then author=UnitName("player") end
    if #message>1000 then if owner then info("Your question is too long.") end; return end
    local owners,guests=counts()
    if owner then
        if owners>=8 then info("Your question queue is full."); return end
    else
        if not settings.allow_others or not settings.share_replies then return end
        local key=string.lower(author)
        local remaining=settings.guest_cooldown_seconds-(time()-(db.lastAccepted[key] or 0))
        if remaining>0 then tell(author,"Please wait " .. math.ceil(remaining) .. " seconds before asking again."); return end
        if pending and string.lower(pending.author)==key then tell(author,"Your previous question is still being answered."); return end
        for _,entry in ipairs(backlog) do
            if string.lower(entry.author)==key then tell(author,"Your previous question is still queued."); return end
        end
        if guests>=settings.max_guest_queue then tell(author,"The question queue is full. Please try again later."); return end
        db.lastAccepted[key]=time()
    end
    sequence=sequence+1
    backlog[#backlog+1]={id=tostring(sequence),author=author,text=message:gsub("[\30\31]"," ")}
    if not pending then beginNext() else draw() end
end)
frame:SetScript("OnUpdate",function(self,elapsed)
    joinTime=joinTime+elapsed; pollTime=pollTime+elapsed; scaleTime=scaleTime+elapsed
    if joinTime>=10 then join(); joinTime=0 end
    if pollTime>=(pending and 6 or 30) and (pending or nextSlot<=SLOT_COUNT) then poll(); pollTime=0 end
    sendTime=sendTime+elapsed
    if sendTime>=1.5 and #outgoing>0 and GetChannelName(CHANNEL)>0 then
        if send(outgoing[1],"CHANNEL",nil,GetChannelName(CHANNEL)) then table.remove(outgoing,1) end
        sendTime=0
    end
    if scaleTime>=2 then
        local h
        if GetPhysicalScreenSize then local w; w,h=GetPhysicalScreenSize() end
        if not h then local resolution=GetCVar and GetCVar("gxResolution") or ""; h=tonumber(resolution:match("x(%d+)")) end
        strip:SetScale(768/(h or 1080)/UIParent:GetEffectiveScale()); scaleTime=0
    end
end)
SLASH_WOWLLMCHAT1="/wllm"
SlashCmdList.WOWLLMCHAT=function(msg)
    if msg=="cancel" then pending=nil; backlog={}; outgoing={}; strip:Hide(); info("Pending questions cancelled.")
    else info("AI channel " .. GetChannelName(CHANNEL) .. "; remaining reply slots: " .. (SLOT_COUNT-nextSlot+1) .. "; waiting: " .. (pending and "yes" or "no")) end
end

-- Preserve the local blue-name rendering without displaying our network echo twice.
ChatFrame_AddMessageEventFilter("CHAT_MSG_CHANNEL",function(self,event,message,author)
    if not readable(message) or not readable(author) then return false end
    if isOwner(author) and message:match("^%[Qwen3 %(MoE%)") then return true end
    return false
end)
