from django.test import TestCase
from django.contrib.auth.models import User
from django.db import IntegrityError
from datetime import date, timedelta

from property.models import Project, PropertyList, TaskList, Task


class ProjectModelTest(TestCase):
    """Test Project model functionality"""

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='testuser1',
            email='test1@test.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='testuser2',
            email='test2@test.com',
            password='testpass123'
        )

    def test_project_creation(self):
        """Project created with correct defaults"""
        project = Project.objects.create(
            owner=self.user1,
            title='My First Project'
        )
        self.assertEqual(project.owner, self.user1)
        self.assertEqual(project.title, 'My First Project')
        self.assertEqual(project.description, '')
        self.assertIsNotNone(project.uuid)
        self.assertIsNotNone(project.created_at)
        self.assertIsNotNone(project.updated_at)

    def test_project_with_description(self):
        """Project can have description"""
        project = Project.objects.create(
            owner=self.user1,
            title='Test Project',
            description='This is a test project'
        )
        self.assertEqual(project.description, 'This is a test project')

    def test_project_uuid_unique(self):
        """Project UUIDs are unique"""
        project1 = Project.objects.create(owner=self.user1, title='Project 1')
        project2 = Project.objects.create(owner=self.user1, title='Project 2')
        self.assertNotEqual(project1.uuid, project2.uuid)

    def test_project_unique_owner_title(self):
        """Project enforces unique owner+title constraint"""
        Project.objects.create(owner=self.user1, title='Same Title')

        with self.assertRaises(IntegrityError):
            Project.objects.create(owner=self.user1, title='Same Title')

    def test_project_same_title_different_owner(self):
        """Different users can have projects with same title"""
        project1 = Project.objects.create(owner=self.user1, title='My Project')
        project2 = Project.objects.create(owner=self.user2, title='My Project')
        self.assertNotEqual(project1.id, project2.id)

    def test_project_str(self):
        """Project string representation"""
        project = Project.objects.create(owner=self.user1, title='Test Project')
        self.assertEqual(str(project), 'Test Project (testuser1)')

    def test_project_viewers(self):
        """Project can have viewers"""
        project = Project.objects.create(owner=self.user1, title='Test Project')
        project.viewers.add(self.user2)

        self.assertEqual(project.viewers.count(), 1)
        self.assertIn(self.user2, project.viewers.all())

    def test_project_contributors(self):
        """Project can have contributors"""
        project = Project.objects.create(owner=self.user1, title='Test Project')
        project.contributors.add(self.user2)

        self.assertEqual(project.contributors.count(), 1)
        self.assertIn(self.user2, project.contributors.all())

    def test_project_property_lists_count(self):
        """Project tracks property lists count"""
        project = Project.objects.create(owner=self.user1, title='Test Project')

        PropertyList.objects.create(
            owner=self.user1,
            project=project,
            title='List 1'
        )
        PropertyList.objects.create(
            owner=self.user1,
            project=project,
            title='List 2'
        )

        self.assertEqual(project.property_lists.count(), 2)

    def test_project_ordering(self):
        """Projects ordered by created_at descending"""
        project1 = Project.objects.create(owner=self.user1, title='First')
        project2 = Project.objects.create(owner=self.user1, title='Second')

        projects = Project.objects.all()
        self.assertEqual(projects[0], project2)
        self.assertEqual(projects[1], project1)


class TaskListModelTest(TestCase):
    """Test TaskList model functionality"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )

    def test_tasklist_creation(self):
        """TaskList created with correct defaults"""
        task_list = TaskList.objects.create(
            project=self.project,
            title='My Tasks'
        )
        self.assertEqual(task_list.project, self.project)
        self.assertEqual(task_list.title, 'My Tasks')
        self.assertEqual(task_list.description, '')
        self.assertIsNotNone(task_list.uuid)
        self.assertIsNotNone(task_list.created_at)

    def test_tasklist_with_description(self):
        """TaskList can have description"""
        task_list = TaskList.objects.create(
            project=self.project,
            title='Tasks',
            description='Important tasks for the project'
        )
        self.assertEqual(task_list.description, 'Important tasks for the project')

    def test_tasklist_uuid_unique(self):
        """TaskList UUIDs are unique"""
        list1 = TaskList.objects.create(project=self.project, title='List 1')
        list2 = TaskList.objects.create(project=self.project, title='List 2')
        self.assertNotEqual(list1.uuid, list2.uuid)

    def test_tasklist_str(self):
        """TaskList string representation"""
        task_list = TaskList.objects.create(
            project=self.project,
            title='Todo List'
        )
        self.assertEqual(str(task_list), 'Todo List (Test Project)')

    def test_tasklist_cascade_delete(self):
        """TaskList deleted when project is deleted"""
        task_list = TaskList.objects.create(
            project=self.project,
            title='Tasks'
        )
        task_list_id = task_list.id

        self.project.delete()

        self.assertFalse(TaskList.objects.filter(id=task_list_id).exists())

    def test_tasklist_tasks_count(self):
        """TaskList tracks tasks count"""
        task_list = TaskList.objects.create(
            project=self.project,
            title='Tasks'
        )

        Task.objects.create(task_list=task_list, title='Task 1')
        Task.objects.create(task_list=task_list, title='Task 2')
        Task.objects.create(task_list=task_list, title='Task 3')

        self.assertEqual(task_list.tasks.count(), 3)


class TaskModelTest(TestCase):
    """Test Task model functionality"""

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='testuser1',
            email='test1@test.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='testuser2',
            email='test2@test.com',
            password='testpass123'
        )
        self.project = Project.objects.create(
            owner=self.user1,
            title='Test Project'
        )
        self.task_list = TaskList.objects.create(
            project=self.project,
            title='Tasks'
        )

    def test_task_creation(self):
        """Task created with correct defaults"""
        task = Task.objects.create(
            task_list=self.task_list,
            title='Fix bug'
        )
        self.assertEqual(task.task_list, self.task_list)
        self.assertEqual(task.title, 'Fix bug')
        self.assertEqual(task.description, '')
        self.assertEqual(task.status, 'TODO')
        self.assertEqual(task.priority, 'MEDIUM')
        self.assertEqual(task.order, 0)
        self.assertIsNone(task.assigned_to)
        self.assertIsNone(task.due_date)
        self.assertIsNone(task.completed_at)
        self.assertIsNotNone(task.uuid)
        self.assertIsNotNone(task.created_at)

    def test_task_with_all_fields(self):
        """Task can be created with all fields"""
        due = date.today() + timedelta(days=7)
        task = Task.objects.create(
            task_list=self.task_list,
            title='Complete feature',
            description='Implement user authentication',
            status='IN_PROGRESS',
            priority='HIGH',
            assigned_to=self.user2,
            due_date=due,
            order=5
        )
        self.assertEqual(task.description, 'Implement user authentication')
        self.assertEqual(task.status, 'IN_PROGRESS')
        self.assertEqual(task.priority, 'HIGH')
        self.assertEqual(task.assigned_to, self.user2)
        self.assertEqual(task.due_date, due)
        self.assertEqual(task.order, 5)

    def test_task_uuid_unique(self):
        """Task UUIDs are unique"""
        task1 = Task.objects.create(task_list=self.task_list, title='Task 1')
        task2 = Task.objects.create(task_list=self.task_list, title='Task 2')
        self.assertNotEqual(task1.uuid, task2.uuid)

    def test_task_str(self):
        """Task string representation"""
        task = Task.objects.create(
            task_list=self.task_list,
            title='Review PR',
            status='IN_PROGRESS'
        )
        self.assertEqual(str(task), 'Review PR (In Progress)')

    def test_task_status_choices(self):
        """Task has valid status choices"""
        task = Task.objects.create(task_list=self.task_list, title='Test')

        # Valid statuses
        for status_value in ['TODO', 'IN_PROGRESS', 'DONE', 'CANCELLED']:
            task.status = status_value
            task.save()
            task.refresh_from_db()
            self.assertEqual(task.status, status_value)

    def test_task_priority_choices(self):
        """Task has valid priority choices"""
        task = Task.objects.create(task_list=self.task_list, title='Test')

        # Valid priorities
        for priority_value in ['LOW', 'MEDIUM', 'HIGH', 'URGENT']:
            task.priority = priority_value
            task.save()
            task.refresh_from_db()
            self.assertEqual(task.priority, priority_value)

    def test_task_cascade_delete(self):
        """Task deleted when task list is deleted"""
        task = Task.objects.create(task_list=self.task_list, title='Task')
        task_id = task.id

        self.task_list.delete()

        self.assertFalse(Task.objects.filter(id=task_id).exists())

    def test_task_assigned_to_nullable(self):
        """Task can exist without assignee"""
        task = Task.objects.create(task_list=self.task_list, title='Task')
        self.assertIsNone(task.assigned_to)

    def test_task_assigned_to_set_null_on_user_delete(self):
        """Task assigned_to set to null when user deleted"""
        task = Task.objects.create(
            task_list=self.task_list,
            title='Task',
            assigned_to=self.user2
        )

        self.user2.delete()
        task.refresh_from_db()

        self.assertIsNone(task.assigned_to)

    def test_task_ordering(self):
        """Tasks ordered by order then created_at descending"""
        task1 = Task.objects.create(
            task_list=self.task_list,
            title='Third',
            order=2
        )
        task2 = Task.objects.create(
            task_list=self.task_list,
            title='First',
            order=0
        )
        task3 = Task.objects.create(
            task_list=self.task_list,
            title='Second',
            order=1
        )

        tasks = Task.objects.all()
        self.assertEqual(tasks[0], task2)  # order=0
        self.assertEqual(tasks[1], task3)  # order=1
        self.assertEqual(tasks[2], task1)  # order=2

    def test_task_get_status_display(self):
        """Task get_status_display works"""
        task = Task.objects.create(
            task_list=self.task_list,
            title='Task',
            status='IN_PROGRESS'
        )
        self.assertEqual(task.get_status_display(), 'In Progress')

    def test_task_get_priority_display(self):
        """Task get_priority_display works"""
        task = Task.objects.create(
            task_list=self.task_list,
            title='Task',
            priority='URGENT'
        )
        self.assertEqual(task.get_priority_display(), 'Urgent')


class ProjectPropertyListIntegrationTest(TestCase):
    """Test Project-PropertyList relationship"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.project = Project.objects.create(
            owner=self.user,
            title='Housing Search'
        )

    def test_propertylist_requires_project(self):
        """PropertyList requires project FK"""
        # Should work with project
        prop_list = PropertyList.objects.create(
            owner=self.user,
            project=self.project,
            title='My List'
        )
        self.assertEqual(prop_list.project, self.project)

    def test_propertylist_cascade_delete_from_project(self):
        """PropertyList deleted when project is deleted"""
        prop_list = PropertyList.objects.create(
            owner=self.user,
            project=self.project,
            title='List'
        )
        list_id = prop_list.id

        self.project.delete()

        self.assertFalse(PropertyList.objects.filter(id=list_id).exists())

    def test_project_multiple_property_lists(self):
        """Project can have multiple property lists"""
        PropertyList.objects.create(
            owner=self.user,
            project=self.project,
            title='London Properties'
        )
        PropertyList.objects.create(
            owner=self.user,
            project=self.project,
            title='Manchester Properties'
        )
        PropertyList.objects.create(
            owner=self.user,
            project=self.project,
            title='Birmingham Properties'
        )

        self.assertEqual(self.project.property_lists.count(), 3)

    def test_propertylist_access_project_attributes(self):
        """PropertyList can access project attributes"""
        prop_list = PropertyList.objects.create(
            owner=self.user,
            project=self.project,
            title='My List'
        )

        self.assertEqual(prop_list.project.title, 'Housing Search')
        self.assertEqual(prop_list.project.owner, self.user)
