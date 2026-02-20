import json
import random
import re
import os
import sys
import xbmc
import xbmcvfs
import xbmcgui
import xbmcplugin
import xbmcaddon
from urllib.parse import parse_qs
#from resources.lib import playermonitor as p

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
HANDLE = int(sys.argv[1])
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
IMG_PATH = xbmcvfs.translatePath(f"special://home/addons/{ADDON_ID}/resources/")
LIST_DIR = os.path.join(PROFILE, "lists")
WINDOW = xbmcgui.Window(10000)

os.makedirs(LIST_DIR, exist_ok=True)

d = xbmcgui.Dialog()

# ---------- Sort Options ----------

TVSHOW_SORT = [
    ("No sorting",lambda shows: shows),
    ("A–Z",lambda shows: sorted(shows, key=lambda s: s["title"].lower())),
    ("Z–A",lambda shows: sorted(shows, key=lambda s: s["title"].lower(), reverse=True)),
    ("Random",lambda shows: random.sample(shows, len(shows))),
    ("Last played", lambda shows: sorted(
        shows,
        key=lambda s: (s.get("lastplayed") is None, s.get("lastplayed") or ""),
        reverse=True
    )),
]


# ---------- Lists manage ----------

def list_path(name):
    safe = name.replace(" ", "_")
    return os.path.join(LIST_DIR, f"{safe}.json")


def load_list(name):
    if not name:
        return
    path = list_path(name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_list(name, data):
    with open(list_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_all_lists():
    return sorted(f[:-5] for f in os.listdir(LIST_DIR) if f.endswith(".json"))

def remove_list(list):
    name = list
    list = list.replace(" ","_")
    #perm = ADDON.getSetting('perm') == 'true'
    perm = 'true'
    dl = delete_file(f"{list}.json",perm)
    if dl:
        d.notification(f"{str(name).upper()}", f"...removed", xbmcgui.NOTIFICATION_INFO, 2000)
    else:
        d.notification(f"{str(name).upper()}", f"Error removing", xbmcgui.NOTIFICATION_INFO, 2000)
    #xbmc.executebuiltin("Container.Refresh")


# ---------- File helpers ----------


def clean_str(s):
    return re.sub(r'[^A-Za-z0-9\-_ ]', '', s)


def delete_file(file,perm):
    try:
        path = os.path.join(LIST_DIR, file)
        if not os.path.isfile(path):
            return False
        if perm:
            os.remove(path)
        else:
            # umbenennen
            dir, file = os.path.split(path)
            name, ext = os.path.splitext(file)
            new_name = f"{name}.baq"
            new_path = os.path.join(dir, new_name)
            os.rename(path, new_path)
        return True
    except Exception as e:
        return False

# ---------- RPC ----------

def rpc(method, params=None):
    payload = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params:
        payload["params"] = params

    try:
        response = xbmc.executeJSONRPC(json.dumps(payload))
        data = json.loads(response)
    except Exception as e:
        xbmc.log(f"[{ADDON_ID}] JSON-RPC Fehler: {e}", xbmc.LOGERROR)
        return {}

    if "error" in data:
        xbmc.log(f"[{ADDON_ID}] JSON-RPC returned error: {data['error']}", xbmc.LOGERROR)
        return {}
    #d.textviewer('RPC',str(data))
    return data.get("result", {})


# ---------- Library ----------

def get_tvshows():
    result = rpc("VideoLibrary.GetTVShows", {"properties": ["title","lastplayed"]})
    return result.get("tvshows", [])


def get_episodes(tvshowid, max_eps):
    result = rpc("VideoLibrary.GetEpisodes",{
                "filter":{
                        "and":[
                            {
                                "field":"playcount",
                                "operator":"lessthan",
                                "value":"1"
                            },
                            {
                                "field":"season",
                                "operator":"greaterthan",
                                "value":"0"
                            }
                            ]
                        },
                            "limits":{
                                        "end":int(max_eps),
                                        "start":0
                                     },
                            "properties":[
                                            "title","playcount","season","episode","showtitle","originaltitle","plot","votes","file",
                                            "rating","ratings","userrating","resume","tvshowid","firstaired","art","streamdetails",
                                            "runtime","director","writer","cast","dateadded","lastplayed"
                                        ],
                            "sort":{"method":"episode","order":"ascending"},
                            "tvshowid":tvshowid
                    })
    #d.ok('Results',str(result))
    unseen = result.get("episodes", [])
    if not unseen:
        return []
    return unseen

# ---------- List creation ----------
def create_list():
    opt = "Create"
    name = xbmcgui.Dialog().input("List name")
    if name:
        edit_list(name,opt)
    
def edit_list(name=None,opt="Edit"):
    cfg = load_list(name)
    if not cfg:
        cfg = {
            "shows": {},
            "max_eps": 4,
            "consecutive": 2,
            "sorting": 0,
            "behavior": "single",
            "autoplay": "false"
            }
    else:
        opt = "Edit"
    name = clean_str(name) 
    shows = get_tvshows()
    shows = sorted(shows, key=lambda s: s["title"])
    show_ids = [s["tvshowid"] for s in shows]
    #d.textviewer('shows',str(shows))
    pl_map = {"single":"playlist","playlist":"single"}
    ap_map = {"false":"true","true":"false"}
    while True:
        ids = show_ids if "all" in cfg["shows"] else cfg["shows"]
        show_lookup = {s["tvshowid"]: s["title"] for s in shows}
        #d.textviewer('show_lookup',str(show_lookup))
        selected_titles = [show_lookup.get(i, "?") for i in cfg["shows"]]
        selected_count = len(ids) if "all" in cfg["shows"] else len(selected_titles)
        shows_label = f"Shows: {selected_count} selected"

        menu = [
            shows_label,
            f"Max episodes per show: {cfg['max_eps']}",
            f"Consecutive episodes: {cfg['consecutive']}",
            f"Sort Method: {TVSHOW_SORT[cfg['sorting']][0]}",
            f"Behavior: {cfg.get('behavior','single')}",
            f"Autoplay: {cfg.get('autoplay','false')}",
            "Save and exit"
        ]
        if opt == "Edit":
            menu.append(f"[COLOR red]... delete list[/COLOR]")
        choice = xbmcgui.Dialog().select(f"{opt}:  {name}", menu)
        if choice == -1:
            return

        if choice == 0:  # edit shows
            titles = ['Select all']
            titles += [s["title"] for s in shows]
            preselect = [i+1 for i, s in enumerate(shows) if s["tvshowid"] in ids]
            if ids == show_ids:
                preselect.append(0)
            #d.ok('preselect',str(preselect))
            result = xbmcgui.Dialog().multiselect("Select shows", titles, preselect=preselect)
            #d.textviewer('result',str(result))
            if result is not None and 0 not in result:
                cfg["shows"] = [shows[i-1]["tvshowid"] for i in result]
            elif result is not None and 0 in result:
                cfg["shows"] = ['all']
                
        elif choice == 1:  # max eps
            val = xbmcgui.Dialog().input("Max episodes per show", str(cfg["max_eps"]), type=xbmcgui.INPUT_NUMERIC)
            if val.isdigit():
                cfg["max_eps"] = int(val)

        elif choice == 2:  # consecutive
            val = xbmcgui.Dialog().input("Consecutive episodes", str(cfg["consecutive"]), type=xbmcgui.INPUT_NUMERIC)
            if val.isdigit():
                cfg["consecutive"] = int(val)

        elif choice == 3: # sort
            labels = [s[0] for s in TVSHOW_SORT]
            sel = xbmcgui.Dialog().select("Sorting Shows", labels)
            if sel != -1:
                cfg["sorting"] = sel
        elif choice == 4:
            cfg["behavior"] = pl_map[cfg.get('behavior','single')] if cfg.get("autoplay") != "true" else "playlist" 
        elif choice == 5:
            cfg["autoplay"] = ap_map[cfg.get('autoplay','false')]
            cfg["behavior"] = "playlist" if cfg.get("autoplay") == "true" else cfg["behavior"]
        elif choice == 6:  # save
            if len(cfg["shows"]) < 1:
                d.notification(f"{str(name).upper()}", f"...no Tvshows selected", xbmcgui.NOTIFICATION_INFO, 2000)
                return
            save_list(name, cfg)
            return
        elif choice == 7: # delete
            if d.yesno(f'Delete "{name.upper()}"',f'really delete "{name.upper()}"?'):
                remove_list(name)
            return


# ---------- Episode handling ----------
def handle_episodes(item):
    #d.textviewer('handle_episodes',str(li))
    director = item.get('director', '')
    writer = item.get('writer', '')
    
    episode_num = f"{item['episode']:02d}"
    season_prefix = 'S' if item['season'] == '0' else f"{item['season']}x"
    label = f"{season_prefix}{episode_num}. {item['title']}"
    
    li_item = xbmcgui.ListItem(label, offscreen=True)
    
    # InfoTagVideo für Kodi 20+
    video_tag = li_item.getVideoInfoTag()
    video_tag.setTitle(item['title'])
    video_tag.setEpisode(item['episode'])
    video_tag.setSeason(item['season'])
    video_tag.setPremiered(item['firstaired'])
    video_tag.setDbId(item['episodeid'])
    video_tag.setPlot(item['plot'])
    video_tag.setTvShowTitle(item['showtitle'])
    video_tag.setOriginalTitle(item['originaltitle'])
    video_tag.setLastPlayed(item['lastplayed'])
    video_tag.setRating(float(item['rating']))
    video_tag.setUserRating(int(float(item['userrating'])))
    video_tag.setVotes(int(item['votes']))
    video_tag.setPlaycount(item['playcount'])
    video_tag.setPath(item['file'])
    video_tag.setDateAdded(item['dateadded'])
    video_tag.setResumePoint(float(item['resume']['position']),float(item['resume']['total']))
    video_tag.setMediaType('episode')
    
    # Director Writer
    if director:
        video_tag.setDirectors([director] if isinstance(director, str) else director)
    if writer:
        video_tag.setWriters([writer] if isinstance(writer, str) else writer)
    
    # Resume-Informationen xxx delete
    #li_item.setProperty('resumetime', str(item['resume']['position']))
    #li_item.setProperty('totaltime', str(item['resume']['total']))
    #li_item.setProperty('season_label', item.get('season_label', ''))
    
    # Art
    li_item.setArt({'icon': 'DefaultTVShows.png',
                    'fanart': item['art'].get('tvshow.fanart', ''),
                    'poster': item['art'].get('tvshow.poster', ''),
                    'banner': item['art'].get('tvshow.banner', ''),
                    'clearlogo': item['art'].get('tvshow.clearlogo') or item['art'].get('tvshow.logo') or '',
                    'landscape': item['art'].get('tvshow.landscape', ''),
                    'clearart': item['art'].get('tvshow.clearart', '')
                    })
    li_item.setArt(item['art'])
    
    if 'video' in item['streamdetails'] and item['streamdetails']['video']:
        for stream in item['streamdetails']['video']:
            if 'duration' in stream:
                video_tag.setDuration(stream['duration'])
    else:
        if item.get('runtime'):
            video_tag.setDuration(item['runtime'])
    
    if item['season'] == '0':
        li_item.setProperty('IsSpecial', 'true')
    
    return li_item, label

#--------- list build ------------

def build_list(name):
    cfg = load_list(name)
    if not cfg:
        return
    
    is_playlist = False if cfg.get("behavior") == "single" else True
    is_autoplay = False if cfg.get("autoplay") == "false" else True
    
    if not is_autoplay:
        xbmcplugin.setContent(HANDLE, 'episodes')
        xbmcplugin.setPluginCategory(HANDLE, f"{name.upper()}")
    
    li = xbmcgui.ListItem(label='')
    items = []

    shows = get_tvshows()
    show_lookup = {s["tvshowid"]: s for s in shows}
    if "all" in cfg["shows"]:
        selected = list(show_lookup.values())
    else:
        selected = [show_lookup[sid] for sid in cfg["shows"] if sid in show_lookup]
    
    sorter = TVSHOW_SORT[cfg.get("sorting", 0)][1] 
    selected = sorter(selected)
    
    eps = []
    for s in selected:
        eps.append(get_episodes(s["tvshowid"], cfg["max_eps"]))
    
    result = []
    s = cfg["consecutive"]
    
    for i in range(0, max(len(lst) for lst in eps), s):
        for lst in eps:
            result.extend(lst[i:i + s])
    
    labelscb = ['..']
    for ep in result:
        url = ep['file']
        li,label = handle_episodes(ep)
        
        # Playlist Test
        #playlist.add(url=url, listitem=li)
        
        labelscb.append(label)
        items.append((url, li, False))
    
    #d.textviewer('labelscb',str(labelscb))
    if not is_autoplay:
        if items:
            xbmcplugin.addDirectoryItems(HANDLE, items)
        xbmcplugin.endOfDirectory(HANDLE)

    if is_playlist:
        # Playlist Test
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        player = xbmc.Player()
        cur_label = 'xxxcozybingexxx'
        while not player.isPlaying():
            xbmc.sleep(100)
            #d.notification(f"CozyBinge", f"{labelscb.index(cur_label)}" if cur_label in labelscb else f"{cur_label}", xbmcgui.NOTIFICATION_INFO, 2000)
            if xbmc.getInfoLabel('ListItem.Label') not in labelscb:
                break
            cur_label = xbmc.getInfoLabel('ListItem.Label') or cur_label
        
        if cur_label in labelscb:
            playlist.clear()
            for i,a in enumerate(items):
                if i > labelscb.index(cur_label) - 2:
                    playlist.add(url=a[0], listitem=a[1])
                    
        elif is_playlist and is_autoplay:
            playlist.clear()
            for i in items:
                playlist.add(url=i[0], listitem=i[1])
            
        if is_autoplay and not xbmc.getCondVisibility('Window.IsActive(10000)'):
            #xbmc.executebuiltin("Dialog.Close(busydialog)")
            xbmc.executebuiltin('Dialog.Close(all, true)')
            xbmc.sleep(100)
            player.play(playlist)
        
# ---------- Menu ----------

def root_menu():
    xbmcplugin.setContent(HANDLE, 'videos')
    xbmcplugin.setPluginCategory(HANDLE, 'tvshows')
    fanart = os.path.join(IMG_PATH, f"fanart.jpg")
    
    li = xbmcgui.ListItem("...New list")
    li.setArt({'fanart':fanart})
    xbmcplugin.addDirectoryItem(HANDLE, f"{sys.argv[0]}?action=new", li, False)
    for name in get_all_lists():
        name = name.replace("_", " ")
        li = xbmcgui.ListItem(name)
        info_tag = li.getVideoInfoTag()
        info_tag.setMediaType('tvshow')
        info_tag.setTitle(name.capitalize())
        #li.setInfo('video', {'title': name, 'mediatype': 'video'})
        li.setArt({'fanart':fanart})
        url = f"{sys.argv[0]}?action=list&list={name}"
        edit_cmd = f"RunPlugin(plugin://{ADDON_ID}/?action=edit&list={name})"
        li.addContextMenuItems([(f"[COLOR goldenrod]Edit[/COLOR]", edit_cmd)])
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)

    xbmcplugin.endOfDirectory(HANDLE)

# ---------- Router ----------

def router(paramstring):
    params = parse_qs(paramstring[1:])
    action = params.get('action', [None])[0]
    play = params.get('play', [''])[0]
    listname = params.get('list', [''])[0]
    #d.ok('router',f"{str(action)} {str(listname)}")
    refresh_at = ["new","edit","del"]
    if action in refresh_at:
        if action == "new":
            create_list()
        elif action == "edit":
            edit_list(listname)
        xbmc.executebuiltin("Container.Refresh")
    elif action == "list" and listname:
        build_list(listname)
    else:
        root_menu()

if __name__ == '__main__':
    router(sys.argv[2])