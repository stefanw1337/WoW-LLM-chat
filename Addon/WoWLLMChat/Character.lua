-- Read-only character snapshot. Never select quests, spend talents, or equip items.
local function call(name,...)
    local fn=_G[name]
    local namespace,method=name:match("^([^%.]+)%.(.+)$")
    if namespace then fn=_G[namespace] and _G[namespace][method] end
    if type(fn)~="function" then return nil end
    local result={pcall(fn,...)}
    if result[1] then
        for i=2,16 do if issecretvalue and issecretvalue(result[i]) then result[i]=nil end end
        return unpack(result,2,16)
    end
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
    local version,build,_,interface=call("GetBuildInfo")
    local client=(interface==16001 and "WoW Forever " or "WoW ") .. clean(version or "3.3.5a")
    add("Snapshot: " .. client .. "; build=" .. clean(build) .. "; observed at " .. time() .. "; realm=" .. clean(call("GetRealmName")))
    if call("InCombatLockdown") then
        return table.concat(lines,"\n") .. "\nCharacter data unavailable during combat. Ask again out of combat."
    end
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
    if not GetNumTalentTabs then
        local configID=call("C_ClassTalents.GetActiveConfigID")
        local config=configID and call("C_Traits.GetConfigInfo",configID)
        if config and config.treeIDs then
            for _,treeID in ipairs(config.treeIDs) do
                for _,nodeID in ipairs(call("C_Traits.GetTreeNodes",treeID) or {}) do
                    local node=call("C_Traits.GetNodeInfo",configID,nodeID)
                    local active=node and node.activeEntry
                    if active and active.entryID and (active.rank or 0)>0 then
                        local entry=call("C_Traits.GetEntryInfo",configID,active.entryID)
                        local definition=entry and call("C_Traits.GetDefinitionInfo",entry.definitionID)
                        local name=definition and (definition.overrideName or call("C_Spell.GetSpellName",definition.spellID))
                        talents[#talents+1]=clean(name or ("entry " .. active.entryID)) .. " rank=" .. active.rank
                    end
                end
            end
            add("Talents: active trait configuration only; separate Legacy trees may be unavailable.")
        else add("Talents: unavailable from this client's active configuration API.") end
    end
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
                local itemName=link:match("%[(.-)%]") or call("C_Item.GetItemInfo",link) or call("GetItemInfo",link) or "uncached"
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
    for index=1,math.min(100,call("C_QuestLog.GetNumQuestLogEntries") or call("GetNumQuestLogEntries") or 0) do
        local title,level,_,_,header,_,complete,_,questID=call("GetQuestLogTitle",index)
        local quest=call("C_QuestLog.GetInfo",index)
        if quest then
            title,level,header,questID=quest.title,quest.level,quest.isHeader,quest.questID
            complete=questID and call("C_QuestLog.IsComplete",questID) and 1 or 0
        end
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
