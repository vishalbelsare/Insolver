import os
import json
from io import StringIO
import pandas as pd

from insolver import InsolverDataFrame
from insolver.wrappers import InsolverGLMWrapper
from insolver.transforms import (InsolverTransform, TransformAge, TransformMapValues,
                                 TransformPolynomizer, TransformAgeGender)


class TransformExp:
    def __init__(self, column_driver_minexp, exp_max=52):
        self.priority = 1
        self.column_driver_minexp = column_driver_minexp
        self.exp_max = exp_max

    @staticmethod
    def _exp(exp, exp_max):
        if pd.isnull(exp):
            exp = None
        elif exp < 0:
            exp = None
        else:
            exp = exp * 7 // 365
        if exp > exp_max:
            exp = exp_max
        return exp

    def __call__(self, df):
        df[self.column_driver_minexp] = df[self.column_driver_minexp].apply(self._exp, args=(self.exp_max,))
        return df


features = ['LicAge', 'Gender', 'MariStat', 'DrivAge', 'HasKmLimit', 'BonusMalus', 'RiskArea',
            'Age_m', 'Age_f', 'Age_m_2', 'Age_f_2']
target = 'ClaimAmount'

train_df = ('LicAge,Gender,MariStat,DrivAge,HasKmLimit,BonusMalus,RiskArea,ClaimAmount\r\n'
            '55,Female,Alone,37,0,95,11.0,3689.5413897281\r\n'
            '346,Male,Other,50,0,50,10.0,791.593957703927\r\n'
            '473,Male,Other,60,0,50,4.0,1096.88972809668\r\n'
            '159,Female,Other,40,1,54,9.0,179.258610271903\r\n'
            '419,Female,Other,66,0,50,3.0,84.4567975830816\r\n'
            '393,Female,Other,58,0,50,9.0,1415.59395770393\r\n')

test_df = ('LicAge,Gender,MariStat,DrivAge,HasKmLimit,BonusMalus,RiskArea,ClaimAmount\r\n'
           '393,Female,Other,58,0,50,9.0,1415.59395770393\r\n')

train_df = InsolverDataFrame(pd.read_csv(StringIO(train_df)))
test_df = pd.read_csv(StringIO(test_df))


InsTransforms = InsolverTransform(train_df, [
    TransformAge('DrivAge', 18, 75),
    TransformExp('LicAge', 57),
    TransformMapValues('Gender', {'Male': 0, 'Female': 1}),
    TransformMapValues('MariStat', {'Other': 0, 'Alone': 1}),
    TransformAgeGender('DrivAge', 'Gender', 'Age_m', 'Age_f', age_default=18, gender_male=0, gender_female=1),
    TransformPolynomizer('Age_m'),
    TransformPolynomizer('Age_f'),
    ])
InsTransforms.ins_transform()
InsTransforms.save('transforms.pickle')

x_train = InsTransforms.loc[InsTransforms.index.tolist()[:-1], features]
y_train = InsTransforms.loc[InsTransforms.index.tolist()[:-1], target]
x_test = InsTransforms.loc[[InsTransforms.index.tolist()[-1]], features]

iglm = InsolverGLMWrapper(backend='h2o', family='gamma', link='log')
iglm.fit(x_train, y_train)
iglm.save_model(name='test_glm_model')

predict = iglm.predict(x_test)


os.environ['model_path'] = './test_glm_model.h2o'
os.environ['transforms_path'] = './transforms.pickle'
os.environ['module_path'] = '../examples/user_transforms.py'

from insolver.serving.flask_app import app


app.testing = True
client = app.test_client()


def test_index_page():
    response = client.get()
    assert response.status_code == 200


request_json = {'df': json.loads(test_df.iloc[0].to_json())}


def test_h2o_model():
    response = app.test_client().post(
        '/predict',
        data=json.dumps(request_json),
        content_type='application/json',
    )

    data = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert round(data['predicted'][0], 7) == round(predict[0], 7)
