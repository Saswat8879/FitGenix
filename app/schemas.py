from marshmallow import Schema, fields

class MealSchema(Schema):
    id = fields.Int()
    name = fields.Str(required=True)
    calories = fields.Float(required=True)
    date = fields.Date()
    time = fields.Time()
    flagged = fields.Bool()
    flag_reason = fields.Str()
