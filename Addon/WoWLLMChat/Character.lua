-- Read-only character snapshot. Never select quests, spend talents, or equip items.
local function call(name,...)
    if type(_G[name])~="function" then return nil end
    local result={pcall(_G[name],...)}
    if result[1] then return unpack(result,2,16) end
end
local function clean(value)
    return tostring(value or "unknown"):gsub("|c%x%x%x%x%x%x%x%x",""):gsub("|r",""):gsub("[%z\1-\31\127|]"," ")
end
function WoWLLMCharacterSnapshot(options)
    options=options or {}
    local lines,size,omitted={},0,0
    local function add(line)
        if size+#line+1<=2520 then lines[#lines+1]=line; size=size+#line+1
        else omitted=omitted+1 end
    end
    add("Snapshot: WoW 3.3.5a; observed at " .. time() .. "; realm=" .. clean(call("GetRealmName")))
    add("Character=" .. clean(call("UnitName","player")) .. "; level=" .. clean(call("UnitLevel","player")) .. "; class=" .. clean(call("UnitClass","player")) .. "; race=" .. clean(call("UnitRace","player")) .. "; faction=" .. clean(call("UnitFactionGroup","player")))
    add("Location=" .. clean(call("GetZoneText")) .. "/" .. clean(call("GetSubZoneText")))
    if options.include_gold then
        local copper=call("GetMoney")
        add("Gold: " .. (type(copper)=="number" and string.format("%dg %ds %dc",math.floor(copper/10000),math.floor(copper/100)%100,copper%100) or "unavailable"))
    end
    if options.include_gearscore then
        local score=call("GearScore_GetScore",call("UnitName","player"),"player")
        add("GearScore: " .. (type(score)=="number" and score>0 and tostring(score) or "unavailable (compatible GearScore addon required)"))
    end
    local stats={}
    for i,name in ipairs({"Str","Agi","Sta","Int","Spi"}) do
        local base,effective=call("UnitStat","player",i)
        stats[#stats+1]=name .. "=" .. clean(effective or base)
    end
    add("Stats: " .. table.concat(stats,", "))
    local group=call("GetActiveTalentGroup") or 1
    local talents={}
    for tab=1,math.min(3,call("GetNumTalentTabs") or 0) do
        local name,_,points=call("GetTalentTabInfo",tab,false,false,group)
        add("Talent tree: " .. clean(name) .. "=" .. clean(points) .. " points; active group=" .. group)
        for index=1,math.min(100,call("GetNumTalents",tab,false,false) or 0) do
            local talent,_,_,_,rank,maxRank=call("GetTalentInfo",tab,index,false,false,group)
            if talent and rank and rank>0 then talents[#talents+1]=clean(talent) .. " " .. rank .. "/" .. clean(maxRank) end
        end
    end
    local slots={"Head","Neck","Shoulder","Shirt","Chest","Waist","Legs","Feet","Wrist","Hands","Ring1","Ring2","Trinket1","Trinket2","Back","MainHand","OffHand","Ranged","Tabard"}
    for slot,name in ipairs(slots) do
        if slot~=4 and slot~=19 then
            local link=call("GetInventoryItemLink","player",slot)
            if link then
                local itemID=link:match("item:(%d+)") or "unknown"
                local itemName=link:match("%[(.-)%]") or call("GetItemInfo",link) or "uncached"
                add("Gear " .. name .. ": " .. clean(itemName) .. " [itemID=" .. itemID .. "]")
            else add("Gear " .. name .. ": empty or unavailable") end
        end
    end
    for _,talent in ipairs(talents) do add("Talent: " .. talent) end
    -- Include profession groups without changing the player's collapsed skill UI.
    local profession=false
    for index=1,math.min(150,call("GetNumSkillLines") or 0) do
        local name,header,_,rank,_,_,maximum=call("GetSkillLineInfo",index)
        if header then profession=(name==TRADE_SKILLS or name==SECONDARY_SKILLS or name=="Professions" or name=="Secondary Skills")
        elseif profession and name then add("Skill: " .. clean(name) .. " " .. clean(rank) .. "/" .. clean(maximum)) end
    end
    for index=1,math.min(100,call("GetNumQuestLogEntries") or 0) do
        local title,level,_,_,header,_,complete,_,questID=call("GetQuestLogTitle",index)
        if title and not header then
            local link=call("GetQuestLink",index)
            questID=questID or (link and link:match("quest:(%d+)"))
            add("Quest: " .. clean(title) .. " [level=" .. clean(level) .. ", id=" .. clean(questID) .. ", complete=" .. tostring(complete==1) .. "]")
        end
    end
    if omitted>0 then lines[#lines+1]="Partial snapshot: " .. omitted .. " additional entries omitted for transport size." end
    lines[#lines+1]="Missing fields are unknown. Collapsed lists may be incomplete. No verified loot-source data."
    return table.concat(lines,"\n")
end
