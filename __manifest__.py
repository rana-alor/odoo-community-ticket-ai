{
    'name':'Ticket Classifier',
    'summary':'tickets classification',
    'author':'Rana Alo',
    'depends': ['mail'],
    'license': 'LGPL-3',
    'data':[
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/menu.xml',
        'views/ticket.xml',
    ],
    'assets': {
        "web.assets_backend": [
            "community_ticket_ai/static/src/css/ticket.css",
        ],
    },

}
