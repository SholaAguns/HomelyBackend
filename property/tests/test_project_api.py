from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import date, timedelta

from property.models import Project, PropertyList, TaskList, Task
from property.serializers import ProjectSerializer, TaskListSerializer, TaskSerializer


class ProjectSerializerTest(TestCase):
    """Test ProjectSerializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )

    def test_project_serializer_fields(self):
        """ProjectSerializer includes correct fields"""
        project = Project.objects.create(
            owner=self.user,
            title='Test Project',
            description='Test description'
        )
        serializer = ProjectSerializer(project)

        data = serializer.data
        self.assertIn('uuid', data)
        self.assertIn('owner', data)
        self.assertIn('title', data)
        self.assertIn('description', data)
        self.assertIn('property_lists_count', data)
        self.assertIn('viewers', data)
        self.assertIn('contributors', data)
        self.assertEqual(data['property_lists_count'], 0)


class TaskListSerializerTest(TestCase):
    """Test TaskListSerializer"""

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

    def test_tasklist_serializer_fields(self):
        """TaskListSerializer includes correct fields"""
        task_list = TaskList.objects.create(
            project=self.project,
            title='My Tasks',
            description='Important tasks'
        )
        serializer = TaskListSerializer(task_list)

        data = serializer.data
        self.assertIn('uuid', data)
        self.assertIn('project_uuid', data)
        self.assertIn('project_title', data)
        self.assertIn('title', data)
        self.assertIn('description', data)
        self.assertIn('tasks_count', data)
        self.assertIn('tasks', data)
        self.assertEqual(data['tasks_count'], 0)
        self.assertEqual(data['project_title'], 'Test Project')


class TaskSerializerTest(TestCase):
    """Test TaskSerializer"""

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
        self.task_list = TaskList.objects.create(
            project=self.project,
            title='Tasks'
        )

    def test_task_serializer_fields(self):
        """TaskSerializer includes correct fields"""
        task = Task.objects.create(
            task_list=self.task_list,
            title='Fix bug',
            status='IN_PROGRESS',
            priority='HIGH'
        )
        serializer = TaskSerializer(task)

        data = serializer.data
        self.assertIn('uuid', data)
        self.assertIn('task_list_uuid', data)
        self.assertIn('title', data)
        self.assertIn('status', data)
        self.assertIn('status_display', data)
        self.assertIn('priority', data)
        self.assertIn('priority_display', data)
        self.assertEqual(data['status'], 'IN_PROGRESS')
        self.assertEqual(data['status_display'], 'In Progress')
        self.assertEqual(data['priority'], 'HIGH')
        self.assertEqual(data['priority_display'], 'High')


class ProjectAPITest(APITestCase):
    """Test Project API endpoints"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.token = RefreshToken.for_user(self.user).access_token
        self.client.cookies['access_token'] = str(self.token)

    def test_create_project(self):
        """POST /api/property/projects/ creates new project"""
        data = {
            'title': 'My Housing Project',
            'description': 'Finding a new home'
        }
        response = self.client.post('/api/property/projects/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'My Housing Project')
        self.assertEqual(response.data['description'], 'Finding a new home')
        self.assertEqual(response.data['owner'], 'testuser')
        self.assertIn('uuid', response.data)

    def test_list_projects(self):
        """GET /api/property/projects/ returns user's projects"""
        Project.objects.create(owner=self.user, title='Project 1')
        Project.objects.create(owner=self.user, title='Project 2')

        response = self.client.get('/api/property/projects/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_project_by_uuid(self):
        """GET /api/property/projects/{uuid}/ returns project"""
        project = Project.objects.create(
            owner=self.user,
            title='Test Project',
            description='Test description'
        )

        response = self.client.get(f'/api/property/projects/{project.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Project')
        self.assertEqual(response.data['description'], 'Test description')

    def test_update_project(self):
        """PATCH /api/property/projects/{uuid}/ updates project"""
        project = Project.objects.create(
            owner=self.user,
            title='Old Title'
        )

        data = {'title': 'New Title', 'description': 'New description'}
        response = self.client.patch(
            f'/api/property/projects/{project.uuid}/',
            data
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'New Title')
        self.assertEqual(response.data['description'], 'New description')

    def test_delete_project(self):
        """DELETE /api/property/projects/{uuid}/ deletes project"""
        project = Project.objects.create(owner=self.user, title='Test Project')

        response = self.client.delete(f'/api/property/projects/{project.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Project.objects.filter(uuid=project.uuid).exists())

    def test_project_with_collaboration(self):
        """Project can have viewers and contributors"""
        user2 = User.objects.create_user(
            username='user2',
            email='user2@test.com',
            password='testpass'
        )

        data = {
            'title': 'Collaborative Project',
            'viewers': ['user2@test.com'],
        }
        response = self.client.post('/api/property/projects/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(uuid=response.data['uuid'])
        self.assertIn(user2, project.viewers.all())

    def test_cannot_access_other_user_project(self):
        """User cannot access another user's project"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass'
        )
        other_project = Project.objects.create(
            owner=other_user,
            title='Other Project'
        )

        response = self.client.get(f'/api/property/projects/{other_project.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_access_project_as_viewer(self):
        """Viewer can access project"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass'
        )
        project = Project.objects.create(owner=other_user, title='Shared Project')
        project.viewers.add(self.user)

        response = self.client.get(f'/api/property/projects/{project.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Shared Project')

    def test_can_access_project_as_contributor(self):
        """Contributor can access project"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass'
        )
        project = Project.objects.create(owner=other_user, title='Shared Project')
        project.contributors.add(self.user)

        response = self.client.get(f'/api/property/projects/{project.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Shared Project')


class TaskListAPITest(APITestCase):
    """Test TaskList API endpoints"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.token = RefreshToken.for_user(self.user).access_token
        self.client.cookies['access_token'] = str(self.token)

        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )

    def test_create_task_list(self):
        """POST /api/property/task-lists/ creates new task list"""
        # Refresh project to ensure it has UUID
        self.project.refresh_from_db()

        data = {
            'project_input': str(self.project.uuid),
            'title': 'Moving Tasks',
            'description': 'Tasks for moving house'
        }
        response = self.client.post('/api/property/task-lists/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Moving Tasks')
        self.assertEqual(response.data['description'], 'Tasks for moving house')

    def test_list_task_lists(self):
        """GET /api/property/task-lists/ returns accessible task lists"""
        TaskList.objects.create(project=self.project, title='List 1')
        TaskList.objects.create(project=self.project, title='List 2')

        response = self.client.get('/api/property/task-lists/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_task_list(self):
        """GET /api/property/task-lists/{uuid}/ returns task list"""
        task_list = TaskList.objects.create(
            project=self.project,
            title='Test List'
        )

        response = self.client.get(f'/api/property/task-lists/{task_list.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test List')

    def test_update_task_list(self):
        """PATCH /api/property/task-lists/{uuid}/ updates task list"""
        task_list = TaskList.objects.create(
            project=self.project,
            title='Old Title'
        )

        data = {'title': 'New Title'}
        response = self.client.patch(
            f'/api/property/task-lists/{task_list.uuid}/',
            data
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'New Title')

    def test_delete_task_list(self):
        """DELETE /api/property/task-lists/{uuid}/ deletes task list"""
        task_list = TaskList.objects.create(
            project=self.project,
            title='Test List'
        )

        response = self.client.delete(f'/api/property/task-lists/{task_list.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TaskList.objects.filter(uuid=task_list.uuid).exists())


class TaskAPITest(APITestCase):
    """Test Task API endpoints"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='testuser2',
            email='test2@test.com',
            password='testpass123'
        )
        self.token = RefreshToken.for_user(self.user).access_token
        self.client.cookies['access_token'] = str(self.token)

        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )
        self.task_list = TaskList.objects.create(
            project=self.project,
            title='Tasks'
        )

    def test_create_task(self):
        """POST /api/property/tasks/ creates new task"""
        # Refresh task_list to ensure it has UUID
        self.task_list.refresh_from_db()

        data = {
            'task_list_input': str(self.task_list.uuid),
            'title': 'Book moving van',
            'description': 'Call removal company',
            'priority': 'HIGH'
        }
        response = self.client.post('/api/property/tasks/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Book moving van')
        self.assertEqual(response.data['description'], 'Call removal company')
        self.assertEqual(response.data['priority'], 'HIGH')
        self.assertEqual(response.data['status'], 'TODO')

    def test_create_task_with_assignment(self):
        """POST /api/property/tasks/ with assigned_to"""
        # Refresh task_list to ensure it has UUID
        self.task_list.refresh_from_db()

        data = {
            'task_list_input': str(self.task_list.uuid),
            'title': 'Paint bedroom',
            'assigned_to': self.user2.id,
            'due_date': str(date.today() + timedelta(days=7))
        }
        response = self.client.post('/api/property/tasks/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['assigned_to'], self.user2.id)
        self.assertEqual(response.data['assigned_to_username'], 'testuser2')

    def test_list_tasks(self):
        """GET /api/property/tasks/ returns accessible tasks"""
        Task.objects.create(task_list=self.task_list, title='Task 1')
        Task.objects.create(task_list=self.task_list, title='Task 2')

        response = self.client.get('/api/property/tasks/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_task(self):
        """GET /api/property/tasks/{uuid}/ returns task"""
        task = Task.objects.create(
            task_list=self.task_list,
            title='Test Task',
            status='IN_PROGRESS'
        )

        response = self.client.get(f'/api/property/tasks/{task.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Task')
        self.assertEqual(response.data['status'], 'IN_PROGRESS')

    def test_update_task_status(self):
        """PATCH /api/property/tasks/{uuid}/ updates task status"""
        task = Task.objects.create(
            task_list=self.task_list,
            title='Test Task',
            status='TODO'
        )

        data = {'status': 'DONE'}
        response = self.client.patch(
            f'/api/property/tasks/{task.uuid}/',
            data
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'DONE')

        task.refresh_from_db()
        self.assertEqual(task.status, 'DONE')

    def test_delete_task(self):
        """DELETE /api/property/tasks/{uuid}/ deletes task"""
        task = Task.objects.create(
            task_list=self.task_list,
            title='Test Task'
        )

        response = self.client.delete(f'/api/property/tasks/{task.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.filter(uuid=task.uuid).exists())

    def test_task_ordering(self):
        """Tasks respect order field"""
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

        response = self.client.get('/api/property/tasks/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['title'], 'First')
        self.assertEqual(response.data[1]['title'], 'Second')
        self.assertEqual(response.data[2]['title'], 'Third')


class PermissionTest(APITestCase):
    """Test permissions for new endpoints"""

    def test_unauthenticated_cannot_access_projects(self):
        """Unauthenticated users cannot access projects"""
        response = self.client.get('/api/property/projects/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_cannot_create_task_list(self):
        """Unauthenticated users cannot create task lists"""
        data = {'title': 'Test'}
        response = self.client.post('/api/property/task-lists/', data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_cannot_create_task(self):
        """Unauthenticated users cannot create tasks"""
        data = {'title': 'Test'}
        response = self.client.post('/api/property/tasks/', data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
