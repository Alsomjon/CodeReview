from django.test import TestCase, Client
from django.urls import reverse

from Instructor.models import Rubric, ScoredRow
from Main.forms import GradeReviewForm
from Main.models import Review
from Users.models import User

with open("tests/test_rubric.json", 'r') as file:
    test_json = file.read()


class BaseCase(TestCase):

    def create_user_matrix(self):
        users = {
            'reviewer-affiliated': User.objects.create_user("reviewer-affiliated", is_reviewer=True),
            'student-affiliated': User.objects.create_user("student-affiliated"),
            'reviewer-not': User.objects.create_user("reviewer-not", is_reviewer=True),
            'student-not': User.objects.create_user("student-not"),
            'super': User.objects.create_superuser("test-instructor"),
        }
        self.users = users

    def create_client_matrix(self):
        clients = {}
        for key in self.users.keys():
            val = self.users.get(key)
            new_client = Client()
            new_client.force_login(val)
            clients[key] = new_client
        self.clients = clients

    def setUp(self) -> None:
        self.create_user_matrix()
        self.create_client_matrix()
        self.clients['super'].post(reverse("rubric-create"), {'name': "Test Review Rubric", 'rubric': test_json})
        self.rubric = Rubric.objects.get(name="Test Review Rubric")
        self.review = Review.objects.create(rubric=self.rubric, schoology_id="03.04.05",
                                            student=self.users['student-affiliated'],
                                            reviewer=self.users['reviewer-affiliated'])


class ReviewAccessTest(BaseCase):
    # noinspection SpellCheckingInspection
    expected = {
        'create': ("--yyy",),
        'edit': ("-ynnn", "-ynnn"),
        'cancel': ("nynnn", "nynnn", "nnnnn"),
        'delete': ("nnnny", "nnnny", "nnnny"),
        'claim': ("-nynn", "nnnnn", "nnnnn"),
        'abandon': ("nnnnn", "ynnnn", "nnnnn"),
        'grade': ("nnnnn", "ynnnn", "nnnnn"),
        'view': ("nnnnn", "nnnnn", "nnnnn")
    }

    def assertResponses(self, expected_key, add_pk=True, http_type='get') -> None:
        target_statuses = self.expected[expected_key]
        if add_pk:
            url = reverse(f'review-{expected_key}', kwargs={'pk': self.review.id})
        else:
            url = reverse(f'review-{expected_key}')
        for index in range(len(target_statuses)):
            target_responses = target_statuses[index]
            self.review.status = index
            self.review.save()
            for code_index, expected in enumerate(target_responses):
                if expected != "-":
                    client = self.clients.get(list(self.clients.keys())[code_index])
                    if http_type == 'get':
                        response = client.get(url)
                    else:
                        response = client.post(url)
                    if expected == "y":
                        self.assertIn(response.status_code, (200, 302))
                    elif expected == "n":
                        self.assertIn(response.status_code, (404, 403))
                    else:
                        self.fail("Invalid Setup Of Expected")

    def test_create(self) -> None:
        self.assertResponses('create', add_pk=False)

    def test_edit(self) -> None:
        self.assertResponses('edit')

    def test_cancel(self) -> None:
        self.assertResponses('cancel')

    def test_delete(self) -> None:
        self.assertResponses('delete')

    def test_claim(self) -> None:
        self.assertResponses('claim', http_type='post')

    def test_abandon(self) -> None:
        self.assertResponses('abandon')

    def test_grade(self) -> None:
        self.assertResponses('grade')

    def test_view(self) -> None:
        try:
            self.assertResponses('view')
        except ScoredRow.DoesNotExist:
            pass


class HomeListTest(BaseCase):
    expected = [
        ("-", "active", "open", "none"),
        ("assigned", "active", "none", "none"),
        ("completed", "completed", "none", "none"),
    ]

    url = reverse("home")

    def assertStatus(self, status_num):
        self.review.status = status_num
        self.review.save()
        for index, group in enumerate(self.expected[status_num]):
            if group != "-":
                response = self.clients.get(list(self.clients.keys())[index]).get(self.url)
                if group == "none":
                    for not_group in ["open", "assigned", "completed", "active"]:
                        self.assertNotIn(self.rubric, response.context.get(not_group, []))
                else:
                    self.assertNotIn(self.rubric, response.context.get(group, []))

    def test_open(self) -> None:
        self.assertStatus(0)

    def test_assigned(self) -> None:
        self.assertStatus(1)

    def test_closed(self) -> None:
        self.assertStatus(2)


class BaseReviewAction(TestCase):
    url_name = ''
    start_reviewer = True
    start_review = True
    start_status = Review.Status.OPEN

    schoology_id = "12.34.56"

    def setUpUsers(self):
        self.reviewer = User.objects.create_user('reviewer', is_reviewer=True)
        self.student = User.objects.create_user('student')
        self.reviewer_client = Client()
        self.student_client = Client()
        self.reviewer_client.force_login(self.reviewer)
        self.student_client.force_login(self.student)
        self.super = User.objects.create_superuser('admin')
        self.super_client = Client()
        self.super_client.force_login(self.super)

    def setUpRubric(self):
        self.super_client.post(reverse('rubric-create'), {'name': "Test Rubric", 'rubric': test_json})
        self.rubric = Rubric.objects.get(name="Test Rubric")

    def setUp(self) -> None:
        self.setUpUsers()
        self.setUpRubric()
        if self.start_review:
            self.review = Review.objects.create(schoology_id=self.schoology_id, student=self.student,
                                                rubric=self.rubric)
            if self.start_reviewer:
                self.review.reviewer = self.reviewer
            self.review.status = self.start_status
            self.review.save()
            self.url = reverse(f'review-{self.url_name}', kwargs={'pk': self.review.id})
        else:
            self.url = reverse(f'review-{self.url_name}')


class ReviewCreateTest(BaseReviewAction):
    url_name = 'create'
    start_review = False
    start_reviewer = False

    def test_create(self) -> None:
        self.student_client.post(self.url, {'schoology_id': self.schoology_id, "rubric": str(self.rubric.id)})
        try:
            self.review = Review.objects.get(schoology_id=self.schoology_id)
        except Review.DoesNotExist:
            self.fail("Review Not Created Successfully")


class ReviewCancelUnclaimedTest(BaseReviewAction):
    url_name = 'cancel'
    start_review = True
    start_reviewer = False

    def test_cancel(self) -> None:
        self.student_client.post(self.url)
        self.assertTrue(Review.objects.filter(schoology_id=self.schoology_id).count() == 0)


class ReviewCancelClaimedTest(ReviewCancelUnclaimedTest):
    start_reviewer = True
    start_status = Review.Status.ASSIGNED


class ReviewEditUnclaimedTest(BaseReviewAction):
    url_name = 'edit'
    start_review = True
    start_reviewer = False

    def test_edit(self) -> None:
        self.student_client.post(self.url, {'schoology_id': "12.34.78", "rubric": self.rubric.id})
        self.assertTrue(Review.objects.filter(schoology_id="12.34.78").count() > 0)


class ReviewEditClaimedTest(ReviewEditUnclaimedTest):
    start_reviewer = True
    start_status = Review.Status.ASSIGNED


class ReviewClaimTest(BaseReviewAction):
    url_name = 'claim'
    start_review = True
    start_reviewer = False

    def test_claim(self) -> None:
        self.reviewer_client.post(self.url)
        new_review = Review.objects.get(schoology_id=self.schoology_id)
        self.assertEqual(int(Review.Status.ASSIGNED), new_review.status)
        self.assertEqual(self.reviewer, new_review.reviewer)


class ReviewAbandonTest(BaseReviewAction):
    url_name = 'abandon'
    start_review = True
    start_reviewer = True
    start_status = Review.Status.ASSIGNED

    def test_abandon(self) -> None:
        self.reviewer_client.post(self.url)
        new_review = Review.objects.get(schoology_id=self.schoology_id)
        self.assertEqual(int(Review.Status.OPEN), new_review.status)
        self.assertIsNone(new_review.reviewer)


class ReviewGradeTest(BaseReviewAction):
    url_name = 'grade'
    start_review = True
    start_reviewer = True
    start_status = Review.Status.ASSIGNED

    def assertScoresEqual(self, source_str, target_str):
        self.reviewer_client.post(self.url, {'scores': source_str, "additional_comments": ""})
        new_review = Review.objects.get(schoology_id=self.schoology_id)
        self.assertEqual(new_review.score_fraction(), target_str)

    def assertBad(self, src_str):
        form = GradeReviewForm({'scores': src_str, "additional_comments": ""}, instance=self.review)
        self.assertFalse(form.is_valid())

    def test_grade(self) -> None:
        self.assertScoresEqual("[5,2]", "7.0/12.0")

    def test_grade_with_na(self) -> None:
        self.assertScoresEqual("[5,-1]", "5.0/10.0")

    def test_grade_not_json(self) -> None:
        self.assertBad("not json")

    def test_grade_non_numeric(self) -> None:
        self.assertBad("[not,numeric]")

    def test_grade_none(self) -> None:
        self.assertBad("[]")

    def test_grade_too_much(self) -> None:
        self.assertBad("[1,1,1,1,1,1]")

    def test_grade_under_limit(self) -> None:
        self.assertBad("[-50,2]")
