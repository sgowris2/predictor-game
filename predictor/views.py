import re
import pytz
from operator import attrgetter
from django.shortcuts import render, redirect
from django.db.models import Max
from django.template.defaulttags import register
from django.forms import formset_factory
from django.utils import timezone
from django.contrib.auth import views
from predictor.models import Team, User, Match, Gameweek, Prediction, PredictionResult, GameweekResult, GameweekAggregateResult, Leaderboard
from predictor.forms import PredictionForm, RegistrationForm

#  Variables
PredictionFormSet = formset_factory(PredictionForm, extra=0)

# Methods
@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

# View Definitions


def index(request):
    if request.user.is_authenticated():
        return redirect('/predictor/home/')
    else:
        return redirect('/predictor/login/')


def error404(request):
    render(request, '/predictor/404.html', status=404)


def login(request, *args, **kwargs):

    if request.user.is_authenticated():
        views.logout(request, *args, **kwargs)

    if request.method == 'POST':
        if not request.POST.get('remember_me', None):
            request.session.set_expiry(60*60*24*30)
    return views.login(request, *args, **kwargs)


def register(request):
    if not request.user.is_authenticated():
        if request.method == 'POST':
            form = RegistrationForm(request.POST)
            try:
                if form.is_valid():
                    form.save()
                    return redirect('/predictor/register_success/')
                else:
                    context = {'form': form}
                    return render(request, 'predictor/register.html', context)
            except:
                context = {'form': form}
                return render(request, 'predictor/register.html', context)
        else:
            context = {'form': RegistrationForm()}
            return render(request, 'predictor/register.html', context)
    else:
        return redirect('/predictor/already_logged_in/')


def register_success(request):
    return render(request, 'predictor/register_success.html')


def already_logged_in(request):
    return render(request, 'predictor/already_logged_in.html')


def home(request):

    if request.user.is_authenticated():

        now = timezone.now()
        try:
            current_gameweek = Gameweek.objects.filter(start_time__lte=now, end_time__gte=now)[0]
            deadline1 = 'Next upcoming deadline'
            deadline2 = current_gameweek.end_time.strftime('%B %d, %Y')
            deadline3 = current_gameweek.end_time.astimezone(pytz.timezone('Europe/London')).strftime('%I:%M%p %Z')
        except:
            deadline2 = 'No upcoming deadline'
            deadline1 = ''
            deadline3 = ''

        try:
            position = Leaderboard.objects.get(user=request.user).rank
        except:
            position = 0

        total_players = User.objects.count()

        try:

            last_gameweek_end_time = GameweekResult.objects.all().aggregate(Max('gameweek__end_time'))['gameweek__end_time__max']
            last_gameweek_result = GameweekAggregateResult.objects.get(gameweek__end_time=last_gameweek_end_time)
        except:
            last_gameweek_result = None
            summary_title = None
            summary_body = None

        summary_title = "A gameweek of upsets"
        summary_body = "A gameweek of upsets saw Liverpool lose to bottom of the table Middlesbrough and the " \
                       "reds of Manchester beating their derby rivals in blue. This meant a low scoring gameweek " \
                       "for most of our predictr players that allowed a lot shuffling in the standings."

        context = {'current_gameweek': current_gameweek,
                   'last_gameweek_result': last_gameweek_result,
                   'deadline1': deadline1,
                   'deadline2': deadline2,
                   'deadline3': deadline3,
                   'position': position,
                   'total_players': total_players,
                   'summary_title': summary_title,
                   'summary_body': summary_body}
        return render(request, 'predictor/home.html', context)
    else:
        return redirect('/predictor/login/')


def predict(request):

    if request.user.is_authenticated():
        show_status_message = False
        save_success = True
        now = timezone.now()

        current_gameweek_number = Gameweek.objects.filter(start_time__lte=now, end_time__gte=now)

        # if there is no gameweek available for the current time, then just display the latest gameweek
        if not current_gameweek_number:
            return redirect('/predictor/gameweek/' + re.findall(r'\d+', Gameweek.objects.order_by('-end_time')[0].name)[0])

        if request.method == 'POST':
            show_status_message = True
            try:
                fs = PredictionFormSet(request.POST)
                data = fs.cleaned_data
                for data_point in data:
                    prediction = Prediction.objects.filter(pk=data_point['id'])[0]
                    prediction.home_score = data_point['home_score']
                    prediction.away_score = data_point['away_score']
                    prediction.save()
                save_success = True
            except:
                save_success = False

        current_gameweek_number = current_gameweek_number[0]
        matches_list = Match.objects.filter(gameweek=current_gameweek_number)
        predictions_list = Prediction.objects.filter(user=request.user).filter(match__in=matches_list)
        predictions_dict = {x.pk: x for x in predictions_list}


        initial_list = []
        for prediction in predictions_list:
            initial_list.append(dict(id=prediction.pk,
                                     home_score=prediction.home_score,
                                     away_score=prediction.away_score))
        fs = PredictionFormSet(initial=initial_list)

        context = {
            'fs': fs,
            'current_gameweek_number': current_gameweek_number,
            'predictions_dict': predictions_dict,
            'show_status_message': show_status_message,
            'save_success': save_success
        }
        return render(request, 'predictor/user_current_gameweek.html', context)
    else:
        return redirect('/predictor/login/')


def gameweek(request, gameweek, username=None):

    if request.user.is_authenticated():
        try:
            if username is None:
                gameweek_user = request.user
            else:
                gameweek_user = User.objects.get(username=username)
        except:
            redirect('predictor/404')

        gameweek_instance = Gameweek.objects.filter(name='Gameweek ' + gameweek)[0]
        now = timezone.now()

        if gameweek_instance:

            if gameweek_instance.end_time <= now:

                try:
                    gameweek_result = GameweekResult.objects.get(user=gameweek_user, gameweek=gameweek_instance)
                except:
                    return render(request, 'predictor/calculating_results.html')

                matches_list = Match.objects.filter(gameweek=gameweek_instance)
                predictions_list = Prediction.objects.filter(user=gameweek_user).filter(match__in=matches_list)
                prediction_results_list = PredictionResult.objects.filter(prediction__in=predictions_list)

                context = {'gameweek': gameweek,
                           'gameweek_user': gameweek_user,
                           'username': username,
                           'matches_list': matches_list,
                           'prediction_results_list': prediction_results_list,
                            'gameweek_result': gameweek_result}
                return render(request, 'predictor/user_gameweek.html', context)

            elif gameweek_instance.start_time <= now and gameweek_instance.end_time >= now:
                return redirect('/predictor/predict')

            else:
                return redirect('/predictor/404')
        else:
            return redirect('/predictor/404')
    else:
        return redirect('/predictor/login/')


def gameweeks(request, username=None):

    if request.user.is_authenticated:
        try:
            if username is None:
                gameweek_user = request.user
            else:
                gameweek_user = User.objects.get(username=username)
        except:
            redirect('predictor/404')

        gameweek_results = list(GameweekResult.objects.filter(user=gameweek_user))
        gameweek_results.sort(key=attrgetter('gameweek.name'), reverse=False)
        total_points = 0
        for result in gameweek_results:
            total_points += result.total_points

        context = {'gameweek_user': gameweek_user,
                   'gameweek_results': gameweek_results,
                   'total_points': total_points}
        return render(request, 'predictor/gameweeks.html', context)
    else:
        return redirect('predictor/login/')


def leaderboard(request):

    if request.user.is_authenticated():

        leaderboard = Leaderboard.objects.all()[:10]
        if not leaderboard:
            return render(request, 'predictor/leaderboard.html')
        else:
            if not any(x.user == request.user for x in leaderboard):
                leaderboard.append(Leaderboard.objects.get(user=request.user))
            context = {'leaderboard': leaderboard}
            return render(request, 'predictor/leaderboard.html', context)
    else:
        return redirect('/predictor/login/')


def about(request):

    return render(request, 'predictor/about.html')