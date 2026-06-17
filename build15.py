import math, statistics as st, json, unicodedata, os, datetime
norm=lambda s:''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c)).lower().replace('.','').strip()
def ln(s):
    t=[w for w in norm(s).split() if w not in('jr','sr','ii','iii')]; return t[-1]
clamp=lambda x,a,b:max(a,min(b,x))
fF=lambda f:1.0 if f is None else clamp(1+0.006*(f-50),0.85,1.15)
mM=lambda h:1.0 if h is None else clamp(1+0.20*((h-1.25)/0.6),0.82,1.18)
pM=lambda w:1.0 if w is None else 1+(0.25 if w<1 else 0.30)*(w-1)
la_window=lambda la:math.exp(-((la-25.0)/14.0)**2)

# ---- ISO sheet (101) ----
ISO_RAW={"Yordan Alvarez":.326,"Byron Buxton":.324,"Kyle Schwarber":.321,"Ben Rice":.318,"Munetaka Murakami":.307,
"Hunter Goodman":.286,"Aaron Judge":.285,"Matt Olson":.284,"James Wood":.277,"Brandon Lowe":.272,"Dillon Dingler":.271,
"Juan Soto":.268,"Corbin Carroll":.266,"Willson Contreras":.266,"Max Muncy":.264,"Jordan Walker":.260,"Colson Montgomery":.259,
"Shea Langeliers":.258,"Ian Happ":.255,"Christian Walker":.255,"Nick Kurtz":.250,"Shohei Ohtani":.246,"Miguel Vargas":.243,
"Jake Bauers":.243,"Bryce Harper":.240,"Tyler Soderstrom":.237,"Casey Schmitt":.234,"Kody Clemens":.232,"Elly De La Cruz":.228,
"CJ Abrams":.228,"Gavin Sheets":.227,"Andy Pages":.226,"Mike Trout":.221,"Pete Alonso":.220,"Junior Caminero":.217,
"Alec Burleson":.209,"Michael Harris":.209,"Oneil Cruz":.208,"Liam Hicks":.208,"Luis Garcia":.205,"Angel Martinez":.204,
"Zach Neto":.202,"Spencer Torkelson":.201,"Freddie Freeman":.199,"Sal Stewart":.198,"Cody Bellinger":.198,
"Pete Crow-Armstrong":.196,"Yandy Diaz":.196,"Brice Turang":.196,"Jake Burger":.192,"Gunnar Henderson":.191,"Willy Adames":.189,
"Ketel Marte":.188,"TJ Rumfield":.185,"Manny Machado":.183,"Jorge Soler":.182,"JP Crawford":.181,"Julio Rodriguez":.180,
"Jose Ramirez":.179,"Spencer Steer":.179,"Rafael Devers":.178,"Seiya Suzuki":.178,"Jonathan Aranda":.177,"Jarren Duran":.176,
"Brooks Lee":.176,"Trent Grisham":.174,"Ryan O'Hearn":.174,"Andrew Benintendi":.172,"Bryan Reynolds":.172,"Jazz Chisholm":.171,
"Spencer Horwitz":.171,"Carter Jensen":.170,"Brandon Marsh":.170,"Ronald Acuna":.169,"Jac Caglianone":.169,"Bobby Witt":.168,
"Isaac Paredes":.165,"Ivan Herrera":.165,"Jacob Young":.164,"Ceddanne Rafaela":.164,"Daylen Lile":.163,"Nolan Arenado":.162,
"Garrett Mitchell":.160,"Michael Busch":.160,"Ozzie Albies":.158,"Josh Jung":.158,"Randy Arozarena":.157,"Matt McLain":.157,
"Bryson Stott":.156,"Riley Greene":.156,"Ernie Clement":.156,"Wilyer Abreu":.155,"Matt Chapman":.153,"Daulton Varsho":.152,
"Ildemaro Vargas":.151,"Brandon Nimmo":.151,"Ezequiel Duran":.148,"JJ Wetherholt":.147,"Chase DeLauter":.146,"Evan Carter":.145}
ISO={norm(k):v for k,v in ISO_RAW.items()}
ISO_FLOOR=min(ISO.values())

# ---- consensus median American odds for the 33-bat betting pool only ----
ODDS_RAW={"Shohei Ohtani":205,"Kyle Schwarber":210,"Junior Caminero":232,"Nick Kurtz":240,"Shea Langeliers":255,"Yordan Alvarez":260,"Hunter Goodman":270,"Juan Soto":290,"Pete Crow-Armstrong":290,"Max Muncy":300,"Mike Trout":315,"Bryce Harper":320,"Byron Buxton":320,"Corey Seager":320,"Michael Busch":325,"Ian Happ":325,"Brandon Lowe":332,"Jordan Walker":340,"Yandy Diaz":345,"Christian Walker":350,"James Wood":355,"JJ Bleday":360,"Eugenio Suarez":362,"Jo Adell":368,"Alec Burleson":370,"Sal Stewart":382,"Kerry Carpenter":382,"Tyler Soderstrom":382,"Andy Pages":385,"Seiya Suzuki":400,"Ketel Marte":405,"Kyle Stowers":422,"Riley Greene":422,"Freddie Freeman":422,"Brandon Nimmo":430,"Bobby Witt":435,"Spencer Steer":445,"Dillon Dingler":445,"Mookie Betts":445,"Zach Neto":450,"Joc Pederson":470,"Max Muncy (ATH)":470,"Salvador Perez":475,"Corbin Carroll":475,"Jared Young":482,"Tyler Stephenson":482,"Wyatt Langford":482,"Jake Burger":482,"Jonathan Aranda":482,"Lars Nootbaar":488,"Spencer Torkelson":488,"Kody Clemens":490,"Lawrence Butler":490,"Bryson Stott":495,"Isaac Paredes":495,"Ryan O'Hearn":495,"Kyle Tucker":495,"Bryan Reynolds":500,"Alex Bregman":508,"Moises Ballesteros":508,"Tyler Callihan":508,"Francisco Alvarez":510,"Royce Lewis":510,"Carlos Cortes":510,"Spencer Horwitz":520,"MJ Melendez":522,"Ryan Ward":522,"JJ Wetherholt":525,"Dansby Swanson":532,"Zack Gelof":535,"Ivan Herrera":558,"Matt McLain":560,"Jackson Merrill":560,"Ezequiel Tovar":560,"Willi Castro":560,"Dylan Crews":570,"Nathaniel Lowe":570,"CJ Abrams":572,"Carson Benge":572,"Manny Machado":572,"Curtis Mead":582,"Jac Caglianone":585,"Kevin McGonigle":585,"Gavin Sheets":588,"Endy Rodriguez":588,"Brandon Marsh":595,"Jose Altuve":595,"Logan O'Hoppe":595,"Keibert Ruiz":600,"Josh Jung":612,"Marcus Semien":615,"Nolan Arenado":615,"Bo Bichette":620,"Kyle Higashioka":630,"Carson Kelly":638,"Daylen Lile":640,"Brett Baty":640,"Josh Bell":662,"TJ Rumfield":675,"Heriberto Hernandez":700,"Cole Carrigg":700,"Lane Thomas":710,"Cam Smith":710,"Trea Turner":725,"Liam Hicks":730,"Cedric Mullins":730,"Brooks Lee":750,"Gabriel Moreno":755,"Tyler Freeman":760,"Troy Johnston":765,"Jimmy Crooks":800,"Nick Fortes":800,"Owen Caissie":820,"J.T. Realmuto":820,"Alec Bohm":820,"Pavin Smith":835,"Rodolfo Duran":850,"Joe Mack":880,"Carter Jensen":900,"Jose Tena":900,"Xander Bogaerts":900,"Nathan Church":900,"Jakob Marsee":920,"Masyn Winn":965,"Jase Bowen":990,"Otto Lopez":1000,"Ryan Waldschmidt":1000,"Maikel Garcia":1040,"Luke Keaschall":1040,"Donovan Walton":1040,"Nick Loftin":1100,"Christian Vazquez":1100,"Nolan Schanuel":1100,"Tommy Troy":1120,"Geraldo Perdomo":1120,"Jake Meyers":1160}
ODDS={norm(k):v for k,v in ODDS_RAW.items()}   # full-board consensus, freshest snapshot

# form arrows for the 33 (note flavor only; TOTAL ignores arrow)
FT_RAW={"Hunter Goodman":"down","Michael Busch":"up","Seiya Suzuki":"flat","Ian Happ":"up","Pete Crow-Armstrong":"down",
"Junior Caminero":"down","Yandy Diaz":"flat","Shohei Ohtani":"up","Max Muncy":"up","Freddie Freeman":"flat","Andy Pages":"flat",
"Kyle Schwarber":"down","Bryce Harper":"up","Nick Kurtz":"up","Shea Langeliers":"down","Tyler Soderstrom":"down","Brandon Lowe":"flat",
"Yordan Alvarez":"down","Christian Walker":"down","Kerry Carpenter":"up","Riley Greene":"down","Juan Soto":"down","Sal Stewart":"flat",
"Eugenio Suarez":"down","JJ Bleday":"up","Byron Buxton":"up","Corey Seager":"down","Mike Trout":"down","Jo Adell":"down",
"Ketel Marte":"down","James Wood":"down","Jordan Walker":"up","Alec Burleson":"up"}
FT={norm(k):v for k,v in FT_RAW.items()}

FULL={'COL':'Rockies','CHC':'Cubs','TB':'Rays','LAD':'Dodgers','MIA':'Marlins','PHI':'Phillies','PIT':'Pirates','ATH':'Athletics',
'DET':'Tigers','HOU':'Astros','NYM':'Mets','CIN':'Reds','MIN':'Twins','TEX':'Rangers','LAA':'Angels','AZ':'Diamondbacks',
'KC':'Royals','WSH':'Nationals','SD':'Padres','STL':'Cardinals'}
# game: gmatch -> gn,gtime,wf,opp_for_away(SP that away hitters face = home SP),opp_for_home(=away SP); hr9 by opp; hands
# ---- auto-pulled inputs from fetch_mlb.py: weather->wf and pitcher HR/9, per matchup ----
# slate_auto_<DATE>.json is produced/refreshed by the GitHub Action; the scorer reads
# it at score time so wf and HR/9 reflect the latest pull (and update through the day).
def load_slate(date):
    try:
        s=json.load(open(f'slate_auto_{date}.json'))
    except Exception as e:
        print(f"  (no slate_auto_{date}.json — wf/HR9 fall back to hardcoded: {e})")
        return {}
    out={}
    for g in s.get('games',[]):
        sp={}; lu={}
        for side in ('away','home'):
            sd=g.get(side,{}) or {}
            spd=sd.get('sp',{}) or {}
            if spd.get('name'): sp[norm(spd['name'])]=spd.get('hr9')
            ab=sd.get('abbrev')
            nset={norm(b.get('name','')) for b in (sd.get('lineup') or []) if b.get('name')}
            if ab and nset: lu[ab]=nset                 # this team's card is POSTED -> confirmed
        out[g.get('matchup','')]={'wf':g.get('wf'),'weather':g.get('weather',{}),'sp':sp,'lu':lu}
    return out
DATE=os.environ.get('SLATE_DATE') or (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=4)).strftime('%Y-%m-%d')
SLATE=load_slate(DATE)

GAMES=[
 # gmatch, gn, gtime, wf, away, home, awaySP(name,hand,hr9 home hitters face), homeSP(name,hand,hr9 away hitters face)
 ('MIA@PHI',1,'6:40 PM',1.02,'MIA','PHI',('Ryan Gusto','RHP',None),('Zack Wheeler','RHP',None)),
 ('KC@WSH', 2,'6:45 PM',1.00,'KC','WSH',('Mitch Spence','RHP',None),('Andrew Alvarez','LHP',None)),
 ('NYM@CIN',3,'7:10 PM',1.03,'NYM','CIN',('Tobias Myers','RHP',None),('Chase Burns','RHP',1.1)),
 ('SD@STL', 4,'7:45 PM',0.98,'SD','STL',('Lucas Giolito','RHP',None),('Dustin May','RHP',0.6)),
 ('COL@CHC',5,'8:05 PM',1.04,'COL','CHC',('Michael Lorenzen','RHP',None),('Shota Imanaga','LHP',1.9)),
 ('MIN@TEX',6,'8:05 PM',1.00,'MIN','TEX',('Mike Paredes','RHP',None),('MacKenzie Gore','LHP',0.8)),
 ('DET@HOU',7,'8:10 PM',1.00,'DET','HOU',('Troy Melton','RHP',None),('Kai-Wei Teng','RHP',None)),
 ('LAA@AZ', 8,'9:40 PM',1.00,'LAA','AZ',('Walbert Urena','RHP',None),('Ryne Nelson','RHP',2.0)),
 ('PIT@ATH',9,'9:40 PM',1.03,'PIT','ATH',('Jared Jones','RHP',None),('J.T. Ginn','RHP',1.0)),
 ('TB@LAD',10,'10:10 PM',1.00,'TB','LAD',('Nick Martinez','RHP',0.7),('Eric Lauer','LHP',None)),
]
# hitter rows per team: name, aT, zone, form, pb, hh, la
ROWS={
'COL':[("Cole Carrigg",77.9,0.003,50,14.6,60.7,25.8),("Hunter Goodman",57.7,0.064,42,9.1,56.4,22.3),("Edouard Julien",56.2,0.041,54,6.0,49.0,13.0),("TJ Rumfield",55.8,0.053,62,4.2,44.5,18.3),("Brett Sullivan",52.2,0.024,57,3.2,36.5,20.3),("Tyler Freeman",51.9,0.081,49,1.8,40.9,15.1),("Troy Johnston",50.3,0.052,71,3.9,43.6,18.1),("Ezequiel Tovar",50.4,0.109,60,5.6,43.2,20.8),("Willi Castro",50.1,0.106,44,4.8,43.1,17.8)],
'CHC':[("Michael Busch",68.6,0.095,46,9.3,48.8,17.7),("Seiya Suzuki",65.7,0.039,59,7.2,51.6,20.9),("Ian Happ",62.9,0.107,54,7.4,50.3,19.3),("Michael Confranco",58.6,0.067,26,6.4,51.3,16.7),("Alex Bregman",57.9,0.044,37,4.6,47.8,21.4),("Pete Crow-Armstrong",58.8,0.127,57,8.0,51.7,21.0),("Moises Ballesteros",52.5,0.046,26,6.5,46.5,14.4),("Carson Kelly",51.7,0.044,41,4.5,43.7,19.9),("Dansby Swanson",49.9,0.045,55,5.7,47.4,15.6)],
'TB':[("Jonathan Aranda",56.2,0.097,47,7.8,55.4,20.6),("Junior Caminero",53.7,0.062,36,7.7,56.9,14.4),("Yandy Diaz",50.1,0.062,58,3.7,54.3,15.4),("Nick Fortes",42.4,0.155,48,2.7,43.0,17.3),("Cedric Mullins",42.0,0.090,44,4.7,44.1,23.7)],
'LAD':[("Shohei Ohtani",72.3,0.087,65,12.6,63.5,17.2),("Max Muncy",68.6,0.134,49,10.7,54.7,20.5),("Mookie Betts",62.9,0.072,52,5.6,45.1,22.0),("Kyle Tucker",60.9,0.097,39,7.3,49.8,19.0),("Freddie Freeman",58.5,0.113,59,6.2,51.9,17.5),("Ryan Ward",58.3,0.050,47,12.0,34.0,22.4),("Alex Call",55.5,0.077,48,2.6,32.8,19.8),("Andy Pages",54.6,0.092,64,6.2,46.7,20.9)],
'MIA':[("Owen Caissie",63.8,0.063,54,8.1,46.8,18.2),("Kyle Stowers",63.4,0.067,50,9.0,58.4,18.1),("Christopher Morel",57.6,0.047,60,8.2,50.5,17.1),("Heriberto Hernandez",54.9,0.067,52,6.2,48.6,17.1),("Connor Norby",53.9,0.036,55,6.8,42.2,18.2),("Jakob Marsee",53.0,0.069,55,4.2,44.9,21.1),("Joe Mack",53.2,0.038,59,1.6,49.2,13.0),("Liam Hicks",50.2,0.070,47,3.5,35.1,14.4),("Otto Lopez",48.5,0.056,43,3.5,42.6,12.7)],
'PHI':[("Kyle Schwarber",73.8,0.100,42,13.1,70.3,19.2),("Bryce Harper",52.4,0.085,66,7.6,55.5,16.3),("J.T. Realmuto",52.0,0.132,37,5.5,54.3,16.2),("Bryson Stott",50.1,0.083,47,3.4,37.5,20.3),("Brandon Marsh",49.7,0.080,56,4.9,51.5,16.1),("Alec Bohm",49.0,0.128,42,3.0,47.9,17.1),("Rafael Marchan",45.2,0.094,59,3.4,30.7,17.6),("Trea Turner",44.4,0.093,31,4.2,48.9,15.9),("Edmundo Sosa",43.1,0.152,57,4.3,43.8,15.6)],
'PIT':[("Esmerlyn Valdez",73.1,0.012,56,9.5,85.9,17.6),("Tyler Callihan",71.6,0.026,59,20.3,70.9,16.8),("Spencer Horwitz",57.3,0.083,54,5.8,41.9,19.5),("Marcell Ozuna",57.1,0.046,28,7.7,52.8,18.3),("Henry Davis",56.3,0.087,57,5.8,55.3,22.3),("Endy Rodriguez",55.9,0.100,48,3.3,48.8,21.5),("Ryan O'Hearn",54.0,0.056,39,4.7,50.9,15.5),("Bryan Reynolds",52.4,0.062,59,6.3,51.5,12.8),("Brandon Lowe",52.6,0.069,51,9.6,51.9,18.7)],
'ATH':[("Nick Kurtz",84.4,0.056,55,8.7,65.3,17.8),("Shea Langeliers",75.7,0.068,52,8.1,52.2,21.3),("Colby Thomas",70.5,0.139,60,8.7,51.0,25.4),("Tyler Soderstrom",68.5,0.062,41,6.4,51.6,15.5),("Carlos Cortes",67.7,0.094,40,6.2,44.6,17.0),("Max Muncy (ATH)",65.8,0.066,29,6.8,48.7,13.8),("Lawrence Butler",63.2,0.075,54,5.1,48.9,16.2),("Zack Gelof",61.3,0.083,63,4.9,45.3,14.9),("Jonah Heim",58.9,0.068,58,4.3,42.5,20.4)],
'DET':[("Spencer Torkelson",80.3,0.039,46,8.8,56.7,20.9),("Riley Greene",79.7,0.061,42,8.2,54.8,15.8),("Kerry Carpenter",78.4,0.046,44,8.5,53.4,20.1),("Jahmai Jones",75.3,0.095,52,7.9,55.3,18.5),("Kevin McGonigle",74.5,0.049,51,6.5,45.4,22.0),("James Outman",72.4,0.038,43,6.7,48.7,19.0),("Dillon Dingler",69.8,0.094,67,6.2,54.3,16.5),("Jake Rogers",67.5,0.043,45,5.4,45.3,20.2),("Wenceel Perez",63.5,0.044,58,5.4,42.5,21.4)],
'HOU':[("Yordan Alvarez",82.2,0.079,63,10.5,59.7,21.5),("Christian Walker",65.8,0.073,42,7.9,53.6,21.0),("Isaac Paredes",62.1,0.069,63,4.9,51.6,21.7),("Cam Smith",58.3,0.068,59,5.9,49.6,15.4),("Jose Altuve",55.3,0.111,49,5.1,37.9,14.3),("Brice Matthews",53.1,0.074,38,6.9,40.2,16.4),("Taylor Trammell",51.8,0.105,51,5.0,41.1,17.5),("Jake Meyers",50.9,0.062,39,3.5,37.3,16.7),("Christian Vazquez",50.1,0.089,40,2.5,34.5,20.3)],
'NYM':[("Juan Soto",77.5,0.070,58,9.1,59.5,15.4),("Jared Young",74.1,0.066,58,10.7,45.7,16.2),("Carson Benge",60.7,0.053,62,5.9,49.5,15.8),("Mark Vientos",58.5,0.070,28,7.3,54.1,15.4),("MJ Melendez",58.0,0.058,60,5.9,54.1,21.6),("Brett Baty",57.2,0.070,54,6.1,49.0,13.0),("Francisco Alvarez",57.0,0.046,61,6.5,52.6,13.9),("Bo Bichette",55.9,0.052,47,4.2,55.0,16.1),("Marcus Semien",54.8,0.055,69,5.3,42.0,19.8)],
'CIN':[("Sal Stewart",75.7,0.087,48,5.0,46.5,21.5),("Eugenio Suarez",72.7,0.079,52,8.7,48.7,18.3),("Will Benson",66.2,0.067,39,8.2,47.1,20.0),("JJ Bleday",64.8,0.059,47,6.5,44.5,21.9),("Nathaniel Lowe",64.0,0.084,53,4.3,49.0,17.4),("Spencer Steer",62.9,0.081,30,5.2,44.0,20.3),("Tyler Stephenson",62.6,0.072,54,5.0,46.3,17.4),("Matt McLain",61.7,0.056,38,4.8,42.6,21.6),("Dane Myers",60.3,0.135,65,3.6,46.5,16.2)],
'MIN':[("Byron Buxton",72.4,0.055,59,13.3,61.2,19.1),("Kody Clemens",59.2,0.046,63,6.2,52.7,20.3),("Royce Lewis",57.2,0.061,48,7.2,47.5,20.5),("Josh Bell",54.9,0.056,31,5.6,49.5,16.3),("Luke Keaschall",52.9,0.045,34,3.0,36.8,15.9),("Trevor Larnach",52.0,0.047,50,6.3,48.9,13.7),("Tristan Gray",52.3,0.028,31,8.1,52.5,21.0),("Victor Caratini",50.8,0.026,53,4.9,46.0,13.8),("Brooks Lee",48.6,0.061,63,4.5,41.2,15.4)],
'TEX':[("Corey Seager",92.4,0.500,43,9.1,54.3,17.6),("Joc Pederson",87.1,0.500,68,8.0,59.1,20.8),("Wyatt Langford",86.7,0.500,48,8.1,54.7,20.7),("Kyle Higashioka",83.6,0.500,53,6.8,51.6,18.9),("Jake Burger",83.7,0.500,44,7.6,55.8,16.5),("Brandon Nimmo",75.5,0.500,55,5.9,54.9,17.5),("Justin Foscue",72.2,0.500,42,5.4,45.0,24.8),("Josh Jung",71.6,0.500,28,4.1,49.1,15.8)],
'LAA':[("Mike Trout",72.8,0.076,52,11.6,55.6,23.0),("Jo Adell",53.6,0.098,36,7.6,54.4,20.0),("Zach Neto",51.6,0.122,58,8.3,51.1,15.9),("Logan O'Hoppe",49.1,0.081,56,7.4,53.6,17.6),("Nolan Schanuel",45.9,0.082,49,2.7,32.2,14.6),("Donovan Walton",45.5,0.050,37,5.3,33.4,15.3),("Trey Mancini",43.3,0.062,47,4.1,46.6,15.4),("Nick Madrigal",41.9,0.086,52,0.5,25.5,11.1)],
'AZ':[("Ketel Marte",77.1,0.097,50,7.8,56.5,14.3),("Corbin Carroll",72.7,0.097,65,6.4,51.9,17.0),("Pavin Smith",67.6,0.054,57,5.8,47.7,14.6),("Gabriel Moreno",64.7,0.169,50,4.2,48.2,15.9),("Nolan Arenado",63.2,0.084,30,4.8,46.3,20.3),("Adrian Del Castillo",62.8,0.056,50,5.1,48.8,20.7),("Tommy Troy",60.4,0.031,44,4.5,34.6,17.4),("Ryan Waldschmidt",58.1,0.040,48,6.3,39.8,20.0),("Geraldo Perdomo",56.8,0.138,63,2.8,34.2,17.3)],
'KC':[("Bobby Witt",68.3,0.085,44,7.2,51.4,22.8),("Jac Caglianone",61.4,0.025,66,8.3,61.1,11.0),("Nick Loftin",59.4,0.059,53,3.3,36.2,14.2),("Maikel Garcia",58.7,0.034,37,2.8,48.3,14.7),("Lane Thomas",58.7,0.039,63,5.5,44.5,19.2),("Michael Massey",57.2,0.086,57,5.3,46.1,20.5),("Carter Jensen",56.5,0.043,73,6.4,48.0,21.6),("Salvador Perez",55.5,0.089,47,8.1,53.9,19.8)],
'WSH':[("James Wood",75.7,0.064,54,6.6,64.4,9.8),("Curtis Mead",62.3,0.056,60,4.3,46.0,19.5),("Keibert Ruiz",58.1,0.067,55,3.1,37.5,17.3),("Andres Chaparro",58.5,0.029,31,4.9,45.8,20.6),("Daylen Lile",58.0,0.062,54,5.0,43.8,20.4),("CJ Abrams",57.8,0.080,65,5.2,44.7,18.2),("Luis Garcia Jr.",57.4,0.064,46,4.6,44.5,12.2),("Jose Tena",53.4,0.076,35,4.8,48.9,12.0),("Dylan Crews",53.3,0.060,66,4.7,43.4,15.3)],
'SD':[("Rodolfo Duran",74.3,0.033,42,14.2,44.5,20.3),("Jase Bowen",62.4,0.095,45,5.1,41.0,16.3),("Jackson Merrill",57.9,0.086,59,5.8,51.6,20.1),("Manny Machado",56.9,0.069,65,6.7,55.6,21.3),("Gavin Sheets",56.4,0.078,39,6.2,53.1,19.3),("Fernando Tatis Jr.",54.6,0.084,71,6.7,56.8,13.1),("Ty France",49.8,0.084,31,4.2,46.6,16.3),("Xander Bogaerts",49.3,0.066,59,4.6,43.4,11.8)],
'STL':[("Lars Nootbaar",72.4,0.500,50,6.6,50.4,16.4),("Nelson Velazquez",72.2,0.500,50,9.5,47.0,16.5),("Ivan Herrera",68.8,0.500,41,5.7,55.2,11.8),("JJ Wetherholt",66.6,0.500,48,4.9,51.4,21.6),("Alec Burleson",64.8,0.500,62,4.5,48.8,16.2),("Jimmy Crooks",61.5,0.500,51,0.0,41.4,18.9),("Jordan Walker",61.7,0.500,64,6.5,54.0,13.9),("Nathan Church",59.2,0.500,37,4.5,38.7,20.4),("Masyn Winn",55.6,0.500,57,2.8,39.1,19.9)],
}
# ---- lineup status ----
# A bat is 'confirmed' ONLY when a posted lineup (slate_auto 'lu') actually contains it.
# Until that team's card posts, everyone on it is 'projected' (never blanket-confirmed).
# SCRATCHED is an optional same-day hand list for known scratches BEFORE lineups post
# (injury/rest); leave it empty otherwise — it must be re-curated each slate, never reused.
SCRATCHED=[]                              # e.g. ["Some Hitter"] for a known same-day scratch
OUTN={norm(x) for x in SCRATCHED}
players={}
for (gm,gn,gt,wf,away,home,asp,hsp) in GAMES:
    _sl=SLATE.get(gm,{})
    if _sl.get('wf') is not None: wf=_sl['wf']            # auto-pulled park/weather wins
    for code,oppSP in ((away,hsp),(home,asp)):   # away hitters face home SP, vice versa
        opp_name,opp_hand,opp_hr9=oppSP
        opp_hr9=_sl.get('sp',{}).get(norm(opp_name),opp_hr9)  # auto-pulled HR/9 wins
        for (nm,aT,z,form,pb,hh,la) in ROWS[code]:
            key=nm; n=norm(nm)
            iso=ISO.get(n); iso_used=iso if iso is not None else ISO_FLOOR
            powraw=pb*hh*la_window(la); lean='Boost' if wf>1.02 else ('Suppress' if wf<0.98 else 'Neutral')
            _lu=_sl.get('lu',{}).get(code)              # posted lineup for this team (None until it posts)
            if _lu:                                      # card POSTED -> status/out from the real lineup
                _in=(n in _lu); _status='confirmed' if _in else 'projected'; _out=(not _in)
            else:                                        # card NOT posted yet -> projected; only explicit hand-scratches sit out
                _status='projected'; _out=(n in OUTN)
            players[key]=dict(nm=key,code=code,team=FULL[code],aT=aT,zonev=z,form=form,pb=pb,hh=hh,la=la,
                iso=(f".{str(iso).split('.')[1]}" if iso is not None else '\u2014'),iso_used=iso_used,powraw=powraw,
                hr9=opp_hr9,wf=wf,game=gn,gmatch=gm,gtime=gt,late=(gn==10),rain=False,out=_out,status=_status,
                opp=[opp_name,opp_hand],oppERA=None,ftrend=FT.get(n,'flat'),odds=ODDS.get(n),soft=(opp_hr9 is None),why=f"{gm.replace('@',' @ ')} ({lean}). Faces {opp_name} ({opp_hand}).")
# ---- percentile/median normalization across the FULL in-lineup pool ----
pool=list(players.values()); raws=sorted(r['powraw'] for r in pool); N=len(raws)
def pct(p): i=p/100*(N-1); lo=int(i); hi=min(lo+1,N-1); return raws[lo]+(raws[hi]-raws[lo])*(i-lo)
p5,p95=pct(5),pct(95)
for r in pool: r['powidx']=round(clamp(100*(r['powraw']-p5)/(p95-p5),0,100)) if p95>p5 else 50
medP=st.median([r['powidx'] for r in pool]); medI=st.median([r['iso_used'] for r in pool])
zs=[r['zonev'] for r in pool if abs(r['zonev']-0.5)>1e-9]; medZ=st.median(zs)
powT=lambda P:clamp(1+0.15*(P-medP)/40,0.85,1.15)
isoT=lambda I:clamp(1+0.08*(I-medI)/0.06,0.92,1.08)
zoneT=lambda z:1.0 if abs(z-0.5)<1e-9 else clamp(1+0.05*(z-medZ)/0.05,0.95,1.05)
for r in pool:
    r['TOTAL']=round(r['aT']*powT(r['powidx'])*isoT(r['iso_used'])*zoneT(r['zonev'])*fF(r['form'])*mM(r['hr9'])*pM(r['wf']),1)
wx={}
WXEMО={'MIA@PHI':('\u2600\ufe0f','open air'),'KC@WSH':('\u26c5','open air'),'NYM@CIN':('\u2600\ufe0f','open air'),
'SD@STL':('\u26c5','open air'),'COL@CHC':('\u2600\ufe0f','wind out, Wrigley'),'MIN@TEX':('\U0001f3df','Dome'),
'DET@HOU':('\U0001f3df','Dome'),'LAA@AZ':('\U0001f3df','Dome'),'PIT@ATH':('\u2600\ufe0f','93\u00b0, Sacramento'),'TB@LAD':('\u26c5','open air')}
for (gm,gn,gt,wf,away,home,asp,hsp) in GAMES:
    em,cond=WXEMО[gm]; lean='Boost' if wf>1.02 else ('Suppress' if wf<0.98 else 'Neutral')
    _sl=SLATE.get(gm,{}); _w=_sl.get('weather',{}); _wf=_sl['wf'] if _sl.get('wf') is not None else wf
    lean=_w.get('lean') or ('Boost' if _wf>1.02 else ('Suppress' if _wf<0.98 else 'Neutral'))
    wx[str(gn)]={'emoji':_w.get('emoji',em),'lean':lean,'factor':_wf,'park':gm,
        'cond':_w.get('cond',cond),'rain':(f"{_w.get('precip')}% rain" if _w.get('precip') is not None else '0% rain')}
# ---- season ledger: carry forward prior state + fold the last graded night ----
# Paths/dates are env-overridable; if the carryover files aren't present (e.g. CI),
# carry a committed season if available, else start a neutral ledger. No day-specific assert.
PRIOR_D = os.environ.get('PRIOR_D','/home/claude/slate0614/D_0614.json')
NIGHT_LOG = os.environ.get('NIGHT_LOG','/home/claude/slate0614/sample_log_0614.json')
NIGHT_DATE = os.environ.get('NIGHT_DATE','2026-06-14')
try:
    prior=json.load(open(PRIOR_D))['meta']['season']
    night=json.load(open(NIGHT_LOG))['nights'][NIGHT_DATE]['tickets']
    cats={k:dict(v) for k,v in prior['cats'].items()}
    for t in night:
        c=cats.setdefault(t['kind'],{'graded':0,'won':0,'units':0.0,'staked':0.0})
        c['graded']+=1; c['won']+=1 if t['won'] else 0
        c['units']=round(c['units']+t['net'],2); c['staked']=round(c['staked']+t['stake'],2)
    hist=list(prior['history']); run=hist[-1]
    for t in night:
        run=round(run+t['net'],2); hist.append(run)
    season={'since':prior['since'],'stake':prior['stake'],'cats':cats,'history':hist}
    _tot=round(sum(c['units'] for c in cats.values()),2)
    print(f"season folded {NIGHT_DATE}: {_tot:+.2f}u")
except Exception as e:
    try:
        season=json.load(open(os.environ.get('SEASON_JSON','season.json')))
        print(f"  (carryover files absent; carried committed season.json)")
    except Exception:
        season={'since':DATE,'stake':1,'cats':{},'history':[0.0]}
        print(f"  (no season carryover available [{e}] — starting neutral ledger)")
maxAT=round(max(r['aT'] for r in pool),1)
meta={'wx':wx,'face':{},'maxAT':maxAT,'season':season,'date':DATE}
json.dump({'players':players,'meta':meta},open('D_0615.json','w'),indent=1)
print(f"maxAT={maxAT}")
# report
print(f"FULL POOL = {len(players)} in-lineup hitters | medians POWER{medP:.0f} ISO{medI:.3f} Zone{medZ:.3f} | p5={p5:.0f} p95={p95:.0f}")
priced=sorted([r for r in pool if r['odds']],key=lambda r:-(100/(r['odds']+100)))[:33]
priced.sort(key=lambda r:-r['TOTAL'])
print(f"\nBETTING POOL (top-33 by implied), re-ranked by full-pool TOTAL:")
print(f"{'#':>2} {'TOTAL':>6} {'aT':>5} {'PWR':>3} {'mM':>4} player (team)")
for i,r in enumerate(priced,1):
    print(f"{i:>2} {r['TOTAL']:6.1f} {r['aT']:5.1f} {r['powidx']:3d} {mM(r['hr9']):4.2f} {r['nm']} ({r['code']})")
print("\nFULL-POOL TOP 12 (incl. non-bet bats):")
for r in sorted(pool,key=lambda r:-r['TOTAL'])[:12]:
    tag='' if r['odds'] else '  (no market)'
    print(f"  {r['TOTAL']:6.1f}  {r['nm']} ({r['code']}){tag}")
