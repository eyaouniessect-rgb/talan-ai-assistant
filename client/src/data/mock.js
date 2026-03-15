export const USERS = {
  consultant: { id:1, name:'Eya Ben Ali', email:'eya@talan.com', role:'consultant', avatar:'EB', initials:'EB' },
  pm: { id:2, name:'Ahmed Karim', email:'ahmed@talan.com', role:'pm', avatar:'AK', initials:'AK' }
}

export const PROJECTS = [
  { id:1, name:'TalanConnect', client:'Attijari Bank', status:'En cours', progress:72, team:4, deadline:'30 Avr 2025', tags:['React','FastAPI'] },
  { id:2, name:'ERP Migration', client:'STEG', status:'En cours', progress:45, team:6, deadline:'15 Jun 2025', tags:['SAP','Python'] },
  { id:3, name:'BI Dashboard', client:'Tunisie Telecom', status:'Terminé', progress:100, team:3, deadline:'01 Mar 2025', tags:['PowerBI'] },
  { id:4, name:'CRM Refonte', client:'Orange Tunisie', status:'En attente', progress:10, team:5, deadline:'01 Sep 2025', tags:['Salesforce'] },
]

export const TICKETS = [
  { id:'TAL-142', title:'Intégration API paiement', project:'TalanConnect', priority:'High', status:'En cours', assignee:'Eya Ben Ali' },
  { id:'TAL-138', title:'Fix dashboard analytics', project:'BI Dashboard', priority:'Medium', status:'Résolu', assignee:'Eya Ben Ali' },
  { id:'TAL-155', title:'Migration base de données', project:'ERP Migration', priority:'High', status:'À faire', assignee:'Eya Ben Ali' },
  { id:'TAL-160', title:'Tests unitaires module RH', project:'TalanConnect', priority:'Low', status:'En cours', assignee:'Eya Ben Ali' },
  { id:'TAL-161', title:'Documentation API', project:'CRM Refonte', priority:'Medium', status:'À faire', assignee:'Eya Ben Ali' },
  { id:'TAL-162', title:'Review code backend', project:'ERP Migration', priority:'High', status:'En cours', assignee:'Eya Ben Ali' },
  { id:'TAL-163', title:'Déploiement staging', project:'TalanConnect', priority:'Medium', status:'À faire', assignee:'Eya Ben Ali' },
]

export const TEAM_MEMBERS = [
  { id:1, name:'Eya Ben Ali', role:'Développeuse Full Stack', project:'TalanConnect', available:true, initials:'EB' },
  { id:2, name:'Sami Trabelsi', role:'Backend Developer', project:'ERP Migration', available:true, initials:'ST' },
  { id:3, name:'Lina Mansour', role:'UI/UX Designer', project:'CRM Refonte', available:false, initials:'LM' },
  { id:4, name:'Youssef Bsir', role:'DevOps Engineer', project:'TalanConnect', available:true, initials:'YB' },
  { id:5, name:'Nour Hamdi', role:'Data Analyst', project:'BI Dashboard', available:true, initials:'NH' },
  { id:6, name:'Mehdi Jlassi', role:'QA Engineer', project:'ERP Migration', available:false, initials:'MJ' },
]

export const NOTIFICATIONS = [
  { id:1, type:'info', title:'Nouveau ticket assigné', desc:'TAL-168 vous a été assigné sur TalanConnect', time:'Il y a 5 min', source:'Jira', read:false },
  { id:2, type:'success', title:'Congé approuvé', desc:'Votre demande de congé du 15 au 21 mars a été approuvée', time:'Il y a 1h', source:'RH', read:false },
  { id:3, type:'warning', title:'Deadline approchante', desc:'Le projet ERP Migration a une deadline dans 3 jours', time:'Il y a 2h', source:'Calendar', read:false },
  { id:4, type:'info', title:'Message Slack', desc:'Ahmed Karim vous a mentionné dans #talan-connect', time:'Il y a 3h', source:'Slack', read:true },
  { id:5, type:'success', title:'Rapport généré', desc:'Le rapport client pour Attijari Bank est prêt', time:'Hier', source:'CRM', read:true },
  { id:6, type:'info', title:'Réunion planifiée', desc:'Stand-up quotidien demain à 9h00', time:'Hier', source:'Calendar', read:true },
]

export const CONVERSATIONS = [
  {
    id:1, title:'Créer un congé du 15 au 21 mars', date:'Aujourd\'hui 14:32',
    agents:['RH','Calendar','Slack'], messageCount:6,
    messages:[
      { role:'user', content:'Je voudrais créer un congé du 15 au 21 mars.', time:'14:30' },
      { role:'assistant', content:'Bien sûr ! Je vais créer votre congé du 15 au 21 mars (5 jours ouvrés).', time:'14:30',
        steps:[
          { status:'done', text:'Intention détectée : création de congé' },
          { status:'done', text:'Permissions vérifiées : autorisé' },
          { status:'done', text:'Agent RH contacté — congé créé (ID: #789)' },
          { status:'done', text:'Calendrier mis à jour via Google Calendar' },
          { status:'done', text:'Notification envoyée à Ahmed Karim sur Slack' },
        ]
      },
      { role:'user', content:'Merci. Combien de jours de congé il me reste ?', time:'14:33' },
      { role:'assistant', content:'Après cette demande, il vous reste **18 jours** de congé annuel pour 2025.', time:'14:33', steps:[] },
    ]
  },
  {
    id:2, title:'Statut de mes tickets Jira', date:'Hier 10:15',
    agents:['Jira'], messageCount:4,
    messages:[
      { role:'user', content:'Quels sont mes tickets Jira en cours ?', time:'10:15' },
      { role:'assistant', content:'Vous avez 3 tickets en cours sur Jira : TAL-142 (High), TAL-155 (High), TAL-160 (Low). Souhaitez-vous plus de détails sur l\'un d\'eux ?', time:'10:15',
        steps:[
          { status:'done', text:'Agent Jira contacté via MCP Atlassian' },
          { status:'done', text:'7 tickets récupérés — filtrés par statut' },
        ]
      },
    ]
  },
  {
    id:3, title:'Rapport projet TalanConnect', date:'Lundi 09:22',
    agents:['CRM','Jira'], messageCount:8,
    messages:[
      { role:'user', content:'Génère un rapport sur l\'avancement du projet TalanConnect.', time:'09:22' },
      { role:'assistant', content:'Voici le rapport TalanConnect : progression à 72%, 4 membres actifs, 3 tickets critiques ouverts, prochaine deadline le 30 avril 2025.', time:'09:22',
        steps:[
          { status:'done', text:'Agent CRM contacté' },
          { status:'done', text:'Agent Jira contacté via MCP' },
          { status:'done', text:'Rapport synthétisé' },
        ]
      },
    ]
  },
]

export const ACTIVITY = [
  { id:1, action:'Congé créé', detail:'15-21 mars 2025', time:'Il y a 2h', icon:'calendar', color:'green' },
  { id:2, action:'Ticket mis à jour', detail:'TAL-142 → En cours', time:'Il y a 4h', icon:'ticket', color:'orange' },
  { id:3, action:'Message Slack envoyé', detail:'Notification à #team-talan', time:'Hier', icon:'message', color:'purple' },
  { id:4, action:'Rapport généré', detail:'Client Attijari Bank', time:'Il y a 2j', icon:'file', color:'blue' },
]
